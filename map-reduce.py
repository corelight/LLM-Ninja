import os
import re
import argparse
import logging
from tika import parser
from bs4 import BeautifulSoup
import tika

# Configure Tika to run in client-only mode.
tika.TikaClientOnly = True

# LangChain imports for Document and text splitting
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Import ChatOllama from langchain_ollama package
from langchain_ollama import ChatOllama

# Global debug flag (set later via command line).
DEBUG = False

def setup_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def safe_invoke(prompt: str) -> str:
    logging.debug("Invoking ChatOllama with prompt of length %d", len(prompt))
    response = chat_model.invoke(prompt)
    content = getattr(response, "content", None)
    if content is None or content.strip() == "":
        raise ValueError("ChatOllama returned an empty response for prompt: " + prompt[:100])
    return content

def extract_text(file_path: str) -> str:
    logging.debug("Extracting text from %s", file_path)
    parsed = parser.from_file(file_path, xmlContent=True)
    content = parsed.get('content', '')
    if not content:
        return ""
    soup = BeautifulSoup(content, 'lxml')
    return soup.get_text(separator="\n").strip()

def crawl_directory_to_documents(directory: str, regex_patterns=None):
    documents = []
    logging.info("Starting directory crawl: %s", directory)
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if regex_patterns and not any(regex.search(file_path) for regex in regex_patterns):
                logging.debug("Skipping file (does not match regex): %s", file_path)
                continue
            logging.info("Ingesting file: %s", file_path)
            try:
                text = extract_text(file_path)
                if text:
                    logging.debug("Extracted %d characters from %s", len(text), file)
                    doc = Document(
                        page_content=text,
                        metadata={"file_name": file, "file_path": file_path}
                    )
                    documents.append(doc)
                else:
                    logging.warning("No text extracted from: %s", file_path)
            except Exception as e:
                logging.error("Error processing %s: %s", file_path, str(e))
    logging.info("Completed directory crawl. Total documents: %d", len(documents))
    return documents

def split_documents(documents, chunk_size, chunk_overlap):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    split_docs = []
    global_index = 0
    logging.info("Starting document splitting with chunk size: {:,} and overlap: {:,}".format(chunk_size, chunk_overlap))
    for doc in documents:
        chunks = splitter.split_text(doc.page_content)
        total_local = len(chunks)
        logging.info("File %s produced %d chunk(s)", doc.metadata['file_name'], total_local)
        for i, chunk in enumerate(chunks, start=1):
            global_index += 1
            new_metadata = doc.metadata.copy()
            new_metadata["chunk_index"] = i
            new_metadata["total_local_chunks"] = total_local
            new_metadata["global_chunk_index"] = global_index
            split_docs.append(Document(page_content=chunk, metadata=new_metadata))
    total_global = len(split_docs)
    for doc in split_docs:
        doc.metadata["global_total_chunks"] = total_global
    logging.info("Document splitting complete. Total chunks: %d", total_global)
    return split_docs

def print_prompt_debug(label, prompt):
    logging.debug("%s prompt length: %d", label, len(prompt))
    if len(prompt) > 400:
        logging.debug("%s prompt first 200 chars: %s...", label, prompt[:200])
        logging.debug("%s prompt last 200 chars: %s", label, prompt[-200:])
    else:
        logging.debug("%s prompt: %s", label, prompt)

def map_stage(chunks, question: str, chunk_size_limit: int):
    map_outputs = []
    logging.info("Starting map stage.")
    complete_chunks = [chunk for chunk in chunks if chunk.metadata.get("total_local_chunks", 1) == 1]
    multi_chunks = [chunk for chunk in chunks if chunk.metadata.get("total_local_chunks", 1) > 1]

    # Group complete files into batches.
    groups = []
    current_group = []
    current_length = 0
    for chunk in complete_chunks:
        length = len(chunk.page_content)
        if current_group and (current_length + length > chunk_size_limit):
            groups.append(current_group)
            logging.info(f"Created a complete file group with {len(current_group):,} file(s) (combined length: {current_length:,})")
            current_group = [chunk]
            current_length = length
        else:
            current_group.append(chunk)
            current_length += length
    if current_group:
        groups.append(current_group)
        logging.info(f"Created a complete file group with {len(current_group):,} file(s) (combined length: {current_length:,})")

    # Process each group of complete files.
    for i, group in enumerate(groups, start=1):
        prompt = (
            "Below are complete documents, each enclosed in <document> tags along with its source file name. "
            "Please use only the texts provided to answer the following question. Do not access external data.\n\n"
        )
        for doc in group:
            file_name = doc.metadata.get("file_name", "unknown")
            prompt += f"Document Source: {file_name}\n<document>\n{doc.page_content}\n</document>\n\n"
        prompt += (
            "Question between <question> ... </question> tags: \n"
            f"<question>\n{question}\n</question>\n\n"
            "Answer the question and include citations referencing the document sources (file names)."
        )
        logging.info("Processing complete file group %d/%d with %d file(s)", i, len(groups), len(group))
        print_prompt_debug("Map (Grouped Complete Files)", prompt)
        answer = safe_invoke(prompt)
        map_outputs.append(answer)

    # Process multi-chunk files individually.
    for chunk in multi_chunks:
        file_name = chunk.metadata.get("file_name", "unknown")
        global_index = chunk.metadata.get("global_chunk_index", "?")
        total_global = chunk.metadata.get("global_total_chunks", "?")
        prompt = (
            "Below is the extracted text from a document chunk between the <chunk> ... </chunk> tags. "
            "Please use only the text below as context to answer the following question. "
            "Do not access external files or databases.\n\n"
            f"Document Source: {file_name}\n"
            f"(Global chunk {global_index} of {total_global})\n\n"
            f"Document Content:\n<chunk>\n{chunk.page_content}\n</chunk>\n\n"
            "Question between <question> ... </question> tags: \n"
            f"<question>\n{question}\n</question>\n\n"
            "Answer the question and include citations referencing the document source (i.e., file name)."
        )
        logging.info("Processing multi-chunk file: %s (chunk %d of %d)", file_name, global_index, total_global)
        print_prompt_debug("Map (Multi-chunk)", prompt)
        answer = safe_invoke(prompt)
        map_outputs.append(answer)

    logging.info("Map stage complete. Total outputs: %d", len(map_outputs))
    return map_outputs

def reduce_stage(map_outputs, question: str, model="phi4", context_size=37500):
    def token_count(text: str) -> int:
        return len(text.split())

    logging.info("Starting reduce stage with %d map outputs.", len(map_outputs))
    # If there's only one output, simply return it.
    if len(map_outputs) == 1:
        logging.info("Single map output detected. No reduction query needed.")
        return map_outputs[0]
    
    combined = "\n".join(map_outputs)
    logging.info("Combined map outputs token count (approx.): {:,}".format(token_count(combined)))
    
    if token_count(combined) > context_size:
        logging.info("Combined output exceeds context limit. Splitting into intermediate chunks.")
        chunks = []
        current_chunk = ""
        for output in map_outputs:
            if current_chunk and token_count(current_chunk + "\n" + output) > context_size:
                chunks.append(current_chunk)
                current_chunk = output
            else:
                current_chunk = current_chunk + "\n" + output if current_chunk else output
        if current_chunk:
            chunks.append(current_chunk)
        logging.info("Created %d intermediate chunk(s) for further reduction.", len(chunks))
        
        intermediate_results = []
        for i, chunk in enumerate(chunks, start=1):
            logging.info("Reducing intermediate chunk %d of %d.", i, len(chunks))
            prompt = (
                "Below are some partial answers produced by processing document chunks between the <partial_content> ... </partial_content> tags. "
                "Based solely on the text provided in these partial answers, please consolidate them into a single answer. "
                "Do not access external data. "
                "Be sure to keep and list all source file names mentioned in the content.\n\n"
                f"<partial_content>\n{chunk}\n</partial_content>\n\n"
                "Intermediate question between <question> ... </question> tags: \n"
                f"<question>\n{question}\n</question>\n\n"
                "Provide a consolidated answer including citations referencing the document sources (file names)."
            )
            logging.debug("Intermediate prompt token count (approx.): %d", token_count(prompt))
            intermediate_result = safe_invoke(prompt)
            intermediate_results.append(intermediate_result)
        return reduce_stage(intermediate_results, question, model, context_size)
    else:
        logging.info("Combined output is within context limit. Finalizing reduction.")
        prompt = (
            "Below are the answers produced by processing document chunks between the <combined_content> ... </combined_content> tags. "
            "Based solely on the text provided in these answers, please consolidate them into a single final answer. "
            "Do not access external data. "
            "Be sure to keep and list all source file names mentioned in the content.\n\n"
            f"<combined_content>\n{combined}\n</combined_content>\n\n"
            "Final question between <question> ... </question> tags: \n"
            f"<question>\n{question}\n</question>\n\n"
            "Provide a consolidated final answer including citations referencing the document sources (file names)."
        )
        logging.debug("Final consolidation prompt token count (approx.): %d", token_count(prompt))
        final_answer = safe_invoke(prompt)
        return final_answer

def main():
    global DEBUG, chat_model

    parser_arg = argparse.ArgumentParser(
        description="Process documents as a knowledge base with Apache Tika and an LLM map-reduce pipeline."
    )
    parser_arg.add_argument("-d", "--directory", type=str, required=True,
                            help="Path to the directory containing files to process.")
    parser_arg.add_argument("-p", "--path", type=str, default=".*",
                            help="Regex pattern(s) to match file paths. Separate multiple regexes with commas. (default: .*)")
    parser_arg.add_argument("-q", "--query", type=str,
                            help="A single query to ask the LLM (overrides --query_file if provided).")
    parser_arg.add_argument("-f", "--query_file", type=argparse.FileType('r'),
                            help="Path to a file containing the multi-line query.")
    parser_arg.add_argument("-m", "--model", type=str, default="phi4",
                            help="The Ollama model used for the queries (default: phi4).")
    parser_arg.add_argument("-c", "--chunk_size", type=int, default=100000,
                            help="Chunk size for splitting the documents (default: 100000).")
    parser_arg.add_argument("-o", "--chunk_overlap", type=int, default=100,
                            help="Chunk overlap for splitting the documents (default: 100).")
    parser_arg.add_argument("-t", "--temperature", type=float, default=0.0,
                            help="Temperature for the ChatOllama model (default: 0.0).")
    parser_arg.add_argument("-x", "--num_ctx", type=int, default=37500,
                            help="Context window size for ChatOllama (default: 37500).")
    parser_arg.add_argument("-u", "--output", type=str,
                            help="If provided, write the final response to the specified file.")
    parser_arg.add_argument("-s", "--tika_server", type=str, default="http://localhost:9998",
                            help="The Tika server endpoint URL (default: http://localhost:9998)")
    parser_arg.add_argument("-z", "--debug", action="store_true",
                            help="Enable debug output")
    args = parser_arg.parse_args()

    DEBUG = args.debug
    setup_logging(DEBUG)

    logging.info("Starting processing with directory: %s", args.directory)
    tika.TikaServerEndpoint = args.tika_server

    if args.query_file:
        query = args.query_file.read()
        args.query_file.close()
    elif args.query:
        query = args.query
    else:
        query = "Summarize the input context."

    chat_model = ChatOllama(
        model=args.model,
        temperature=args.temperature,
        num_ctx=args.num_ctx,
        num_predict=-2,
        seed=3,
        keep_alive=-1
    )

    regex_patterns = [re.compile(pattern.strip()) for pattern in args.path.split(',')]
    documents = crawl_directory_to_documents(args.directory, regex_patterns)
    split_docs = split_documents(documents, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    
    logging.info("Starting map stage with complete and multi-chunk files.")
    map_outputs = map_stage(split_docs, query, chunk_size_limit=args.chunk_size)
    if not map_outputs:
        logging.error("No outputs from the map stage. Exiting.")
        return

    final_answer = reduce_stage(map_outputs, query, model=args.model, context_size=args.num_ctx)
    
    print("Final Answer:")
    print(final_answer)

    if args.output:
        try:
            with open(args.output, 'w') as outfile:
                outfile.write(final_answer)
            logging.info("Final response written to %s", args.output)
        except Exception as e:
            logging.error("Error writing final response to %s: %s", args.output, str(e))

if __name__ == "__main__":
    main()
