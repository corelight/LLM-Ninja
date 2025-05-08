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

# Global debug flag and flags for printing responses and queries (set later via command line).
DEBUG = False
PRINT_ALL_RESPONSES = False
SHOW_FULL_QUERY = False

# Global counters for LLM queries
llm_queries_completed = 0
llm_total_queries = 0

def setup_logging(debug: bool, log_to_file: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    if log_to_file:
        # Add a file handler that writes logs to map-reduce.log
        file_handler = logging.FileHandler("map-reduce.log")
        file_handler.setLevel(level)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)

def safe_invoke(prompt: str) -> str:
    global llm_queries_completed, llm_total_queries, PRINT_ALL_RESPONSES, SHOW_FULL_QUERY
    logging.debug(f"Invoking ChatOllama with prompt of length {len(prompt):,}")
    # Log the full prompt if debugging is enabled.
    if DEBUG:
        logging.debug("Full Prompt: " + prompt)
    # If -e is set, print and log the full LLM query.
    if SHOW_FULL_QUERY:
        query_output = "LLM Query:\n" + prompt + "\n" + ("-" * 80)
        logging.info(query_output)
    response = chat_model.invoke(prompt)
    content = getattr(response, "content", None)
    if content is None or content.strip() == "":
        raise ValueError("ChatOllama returned an empty response for prompt: " + prompt)
    # Log the full LLM response if debugging is enabled.
    if DEBUG:
        logging.debug("LLM Full Response: " + content)
    # If -n is set, print and log the full LLM response.
    if PRINT_ALL_RESPONSES:
        response_output = "LLM Response:\n" + content + "\n" + ("-" * 80)
        logging.info(response_output)
    llm_queries_completed += 1
    logging.info(f"LLM queries completed: {llm_queries_completed}/{llm_total_queries}")
    return content

def extract_text(file_path: str) -> str:
    logging.debug(f"Extracting text from {file_path}")
    parsed = parser.from_file(file_path, xmlContent=True)
    content = parsed.get('content', '')
    if not content:
        return ""
    soup = BeautifulSoup(content, 'lxml')
    return soup.get_text(separator="\n").strip()

def crawl_directory_to_documents(directory: str, regex_patterns=None):
    documents = []
    logging.info(f"Starting directory crawl: {directory}")
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if regex_patterns and not any(regex.search(file_path) for regex in regex_patterns):
                logging.debug(f"Skipping file (does not match regex): {file_path}")
                continue
            logging.info(f"Ingesting file: {file_path}")
            try:
                text = extract_text(file_path)
                if text:
                    logging.debug(f"Extracted {len(text):,} characters from {file}")
                    doc = Document(
                        page_content=text,
                        metadata={"file_name": file, "file_path": file_path}
                    )
                    documents.append(doc)
                else:
                    logging.warning(f"No text extracted from: {file_path}")
            except Exception as e:
                logging.error(f"Error processing {file_path}: {str(e)}")
    logging.info(f"Completed directory crawl. Total documents: {len(documents):,}")
    return documents

def split_documents(documents, chunk_size, chunk_overlap):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    split_docs = []
    global_index = 0
    logging.info(f"Starting document splitting with chunk size: {chunk_size:,} and overlap: {chunk_overlap:,}")
    for doc in documents:
        chunks = splitter.split_text(doc.page_content)
        total_local = len(chunks)
        logging.info(f"File {doc.metadata['file_name']} produced {total_local:,} chunk(s)")
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
    logging.info(f"Document splitting complete. Total chunks: {total_global:,}")
    return split_docs

def print_prompt_debug(label, prompt):
    # Always log the full prompt without any truncation.
    logging.debug(f"{label} prompt (full): {prompt}")

def map_stage(chunks, question: str, chunk_size_limit: int):
    global llm_total_queries
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
    num_complete_groups = len(groups)

    # Group multi-chunk files by file name.
    multi_files = {}
    for chunk in multi_chunks:
        file_name = chunk.metadata.get("file_name", "unknown")
        multi_files.setdefault(file_name, []).append(chunk)
    total_multi_chunks = sum(len(chunks_list) for chunks_list in multi_files.values())

    # Estimate total queries for the map stage.
    expected_map_queries = num_complete_groups + total_multi_chunks
    # Add 1 for the reduce stage if there will be more than one map output.
    expected_reduce_queries = 1 if expected_map_queries > 1 else 0
    llm_total_queries = expected_map_queries + expected_reduce_queries
    logging.info(f"Estimated total LLM queries (initial): {llm_total_queries}")

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
        logging.info(f"Processing complete file group {i:,}/{len(groups):,} with {len(group):,} file(s)")
        print_prompt_debug("Map (Grouped Complete Files)", prompt)
        answer = safe_invoke(prompt)
        map_outputs.append(answer)

    # Process each multi-chunk file.
    total_multi_files = len(multi_files)
    multi_chunk_counter = 0
    logging.info(f"Found {total_multi_files:,} multi-chunk file(s) with a total of {total_multi_chunks:,} multi-chunk(s).")
    
    for file_index, (file_name, chunks_list) in enumerate(multi_files.items(), start=1):
        # Sort chunks by the local chunk index (starting at 1 for each file).
        chunks_list.sort(key=lambda c: c.metadata.get("chunk_index", 0))
        total_chunks_for_file = len(chunks_list)
        logging.info(f"Processing multi-chunk file {file_index:,}/{total_multi_files:,}: {file_name} with {total_chunks_for_file:,} chunk(s)")
        for chunk in chunks_list:
            multi_chunk_counter += 1
            local_index = chunk.metadata.get("chunk_index", 0)
            total_local = chunk.metadata.get("total_local_chunks", 0)
            global_index = chunk.metadata.get("global_chunk_index", "?")
            global_total = chunk.metadata.get("global_total_chunks", "?")
            logging.info(f"Processing multi-chunk chunk {multi_chunk_counter:,} of {total_multi_chunks:,} (File: {file_name}, local chunk {local_index:,} of {total_local:,}; global: {global_index} of {global_total})")
            prompt = (
                "Below is the extracted text from a document chunk between the <chunk> ... </chunk> tags. "
                "Please use only the text below as context to answer the following question. "
                "Do not access external files or databases.\n\n"
                f"Document Source: {file_name}\n"
                f"(Chunk {local_index:,} of {total_local:,}; Global chunk {global_index} of {global_total}; "
                f"Multi-chunk progress: {multi_chunk_counter:,} of {total_multi_chunks:,})\n\n"
                f"Document Content:\n<chunk>\n{chunk.page_content}\n</chunk>\n\n"
                "Question between <question> ... </question> tags: \n"
                f"<question>\n{question}\n</question>\n\n"
                "Answer the question and include citations referencing the document source (i.e., file name)."
            )
            print_prompt_debug("Map (Multi-chunk)", prompt)
            answer = safe_invoke(prompt)
            map_outputs.append(answer)

    logging.info(f"Map stage complete. Total outputs: {len(map_outputs):,}")
    return map_outputs

def reduce_stage(map_outputs, question: str, model="phi4", context_size=37500):
    global llm_total_queries
    def token_count(text: str) -> int:
        return len(text.split())

    logging.info(f"Starting reduce stage with {len(map_outputs):,} map outputs.")
    # If there's only one output, simply return it.
    if len(map_outputs) == 1:
        logging.info("Single map output detected. No reduction query needed.")
        return map_outputs[0]

    # Wrap each map output in <output> tags
    tagged_outputs = [f"<output>\n{output}\n</output>" for output in map_outputs]

    # Combine all tagged outputs
    combined = "\n".join(tagged_outputs)
    logging.info(f"Combined map outputs token count (approx.): {token_count(combined):,}")

    # If the combined output exceeds the context size, split into intermediate chunks.
    if token_count(combined) > context_size:
        logging.info("Combined output exceeds context limit. Splitting into intermediate chunks.")
        chunks = []
        current_chunk = ""
        for output in tagged_outputs:
            if current_chunk and token_count(current_chunk + "\n" + output) > context_size:
                chunks.append(current_chunk)
                current_chunk = output
            else:
                current_chunk = current_chunk + "\n" + output if current_chunk else output
        if current_chunk:
            chunks.append(current_chunk)
        logging.info(f"Created {len(chunks):,} intermediate chunk(s) for further reduction.")
        # If more than one reduce query is needed at this level, update the total dynamically.
        if len(chunks) > 1:
            additional_expected = len(chunks) - 1
            llm_total_queries += additional_expected
            logging.info(f"Additional estimated LLM queries from reduce splitting: {additional_expected} (New total: {llm_total_queries})")

        intermediate_results = []
        for i, chunk in enumerate(chunks, start=1):
            logging.info(f"Reducing intermediate chunk {i:,} of {len(chunks):,}.")
            prompt = (
                "Below are some partial answers produced by processing document chunks between the <partial_content> <output> ... </output> ... </partial_content> tags. "
                "Please consolidate them into a single answer based solely on the text provided. "
                "Do not access external data. Be sure to keep and list all source file names mentioned.\n\n"
                f"<partial_content>\n{chunk}\n</partial_content>\n\n"
                "Intermediate question between <question> ... </question> tags:\n"
                f"<question>\n{question}\n</question>\n\n"
                "Provide a consolidated answer including citations referencing the document sources (file names)."
            )
            logging.debug(f"Intermediate prompt token count (approx.): {token_count(prompt):,}")
            intermediate_result = safe_invoke(prompt)
            intermediate_results.append(intermediate_result)
        # Recursively reduce the intermediate results.
        return reduce_stage(intermediate_results, question, model, context_size)
    else:
        logging.info("Combined output is within context limit. Finalizing reduction.")
        prompt = (
            "Below are the answers produced by processing document chunks between the <combined_content> <output> ... </output> ... </combined_content> tags. "
            "Based solely on the text provided, please consolidate them into a single final answer. "
            "Do not access external data. Be sure to keep and list all source file names mentioned.\n\n"
            f"<combined_content>\n{combined}\n</combined_content>\n\n"
            "Final question between <question> ... </question> tags:\n"
            f"<question>\n{question}\n</question>\n\n"
            "Provide a consolidated final answer including citations referencing the document sources (file names)."
        )
        logging.debug(f"Final consolidation prompt token count (approx.): {token_count(prompt):,}")
        final_answer = safe_invoke(prompt)
        return final_answer

def main():
    global DEBUG, chat_model, PRINT_ALL_RESPONSES, SHOW_FULL_QUERY

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
    parser_arg.add_argument("-c", "--chunk_size", type=int, default=65000,
                            help="Chunk size for splitting the documents (default: 65000).")
    parser_arg.add_argument("-o", "--chunk_overlap", type=int, default=0,
                            help="Chunk overlap for splitting the documents (default: 0).")
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
    parser_arg.add_argument("-l", "--log", action="store_true",
                            help="If provided, save log to map-reduce.log in the current directory.")
    parser_arg.add_argument("-n", "--print_responses", action="store_true",
                            help="Output all LLM responses as they happen.")
    parser_arg.add_argument("-e", "--print_queries", action="store_true",
                            help="Show the full LLM queries (prompt text) in the output as they happen.")
    args = parser_arg.parse_args()

    DEBUG = args.debug
    PRINT_ALL_RESPONSES = args.print_responses
    SHOW_FULL_QUERY = args.print_queries
    setup_logging(DEBUG, log_to_file=args.log)

    logging.info(f"Starting processing with directory: {args.directory}")
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
            logging.info(f"Final response written to {args.output}")
        except Exception as e:
            logging.error(f"Error writing final response to {args.output}: {str(e)}")

if __name__ == "__main__":
    main()
