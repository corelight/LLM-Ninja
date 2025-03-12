import os
import re
import argparse
from tika import parser
from bs4 import BeautifulSoup
import tika

# Configure Tika to use your manually started Tika server.
tika.TikaClientOnly = True
tika.TikaServerEndpoint = "http://localhost:9998"

# LangChain imports for Document and text splitting
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Import ChatOllama from langchain_ollama package
from langchain_ollama import ChatOllama

# Import LangGraph modules
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# Global debug flag (set later via command line).
DEBUG = False

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# --------------------------
# Helper: Invoke ChatOllama and return its text content
# --------------------------
def safe_invoke(prompt: str) -> str:
    response = chat_model.invoke(prompt)
    content = getattr(response, "content", None)
    if content is None or content.strip() == "":
        raise ValueError("ChatOllama returned an empty response for prompt: " + prompt[:100])
    return content

# --------------------------
# Extraction Functions (using Tika)
# --------------------------
def extract_text(file_path: str) -> str:
    parsed = parser.from_file(file_path, xmlContent=True)
    content = parsed.get('content', '')
    if not content:
        return ""
    soup = BeautifulSoup(content, 'lxml')
    return soup.get_text(separator="\n").strip()

def crawl_directory_to_documents(directory: str, regex_patterns=None):
    documents = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            # If regex patterns are provided, skip files that do not match any pattern.
            if regex_patterns and not any(regex.search(file_path) for regex in regex_patterns):
                continue
            # Status output to indicate ingestion of a file.
            print(f"Ingesting file: {file_path}")
            debug_print(f"Processing: {file_path}")
            try:
                text = extract_text(file_path)
                if text:
                    debug_print(f"Extracted {len(text)} characters from {file}")
                    doc = Document(
                        page_content=text,
                        metadata={"file_name": file, "file_path": file_path}
                    )
                    documents.append(doc)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
    return documents

def split_documents(documents, chunk_size, chunk_overlap):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    split_docs = []
    global_index = 0
    for doc in documents:
        chunks = splitter.split_text(doc.page_content)
        total_local = len(chunks)
        # Status output: report how many chunks were produced for the current file.
        print(f"File {doc.metadata['file_name']} produced {total_local} chunks.")
        debug_print(f"Document {doc.metadata['file_name']} split into {total_local} chunks.")
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
    debug_print(f"Total global chunks: {total_global}")
    return split_docs

# --------------------------
# Utility: Print prompt debug info
# --------------------------
def print_prompt_debug(label, prompt):
    prompt_length = len(prompt)
    debug_print(f"{label} prompt length: {prompt_length}")
    if prompt_length > 400:
        debug_print(f"{label} prompt first 200 chars:\n{prompt[:200]}...\n")
        debug_print(f"{label} prompt last 200 chars:\n{prompt[-200:]}\n")
    else:
        debug_print(f"{label} prompt:\n{prompt}\n")

# --------------------------
# Map Stage: Process each chunk individually.
# --------------------------
def map_stage(chunks, question: str):
    map_outputs = []
    for chunk in chunks:
        file_name = chunk.metadata.get("file_name", "unknown")
        global_index = chunk.metadata.get("global_chunk_index", "?")
        total_global = chunk.metadata.get("global_total_chunks", "?")
        # Status output: indicate that a chunk is being sent to the model.
        print(f"[Map] Sending chunk from {file_name} (chunk {global_index}/{total_global}) to the model...")
        debug_print(f"\n[Map] Processing {file_name}: Global chunk {global_index} of {total_global}")
        prompt = (
            "Below is the extracted text from a document chunk between the <chunk> ... </chunk> tags. "
            "Please use only the text below as context to answer the following question. "
            "Do not access external files or databases.\n\n"
            f"Document Source: {file_name}\n"
            f"(Global chunk {global_index} of {total_global})\n\n"
            f"Document Content:\n<chunk>\n{chunk.page_content}\n</chunk>\n\n"
            f"Question between <question> ... </question> tags: \n<question>\n{question}\n</question>\n\n"
            "Answer the question and include citations referencing the document source (i.e., file name)."
        )
        debug_print("[Map] Prompt debug:")
        print_prompt_debug("Map", prompt)
        answer = safe_invoke(prompt)
        debug_print("[Map] Answer:")
        debug_print(answer, "\n")
        map_outputs.append(answer)
    return map_outputs

# --------------------------
# Reduce Stage: Consolidate all map outputs with approximate token-aware chunking.
# --------------------------
def reduce_stage(map_outputs, question: str, model="phi4", context_size=37500):
    """
    Recursively reduce map outputs until the combined text fits within the context size.
    The prompt instructs the model to retain and list all source file names mentioned in the content.
    If there is only one map output, skip directly to the final consolidation prompt.
    """
    # Approximate token count by splitting text into words.
    def token_count(text: str) -> int:
        return len(text.split())
    
    print("[Reduce] Starting reduction stage...")

    if len(map_outputs) == 1:
        print("[Reduce] Only one chunk detected. Sending final prompt to model...")
        final_content = map_outputs[0]
        prompt = (
            "Below is the answer produced by processing a single document chunk between the <combined_content> ... </combined_content> tags. "
            "Based solely on the text provided in this answer, please consolidate it into a final answer. "
            "Do not access external data. "
            "Be sure to keep and list all source file names mentioned in the content.\n\n"
            f"<combined_content>\n{final_content}\n</combined_content>\n\n"
            f"Final question between <question> ... </question> tags: \n<question>\n{question}\n</question>\n\n"
            "Provide a consolidated final answer including citations referencing the document sources (file names)."
        )
        debug_print(f"[Reduce] Final prompt token count (approx.): {token_count(prompt)} tokens.")
        return safe_invoke(prompt)
    
    combined = "\n".join(map_outputs)
    print("[Reduce] Combining map outputs for reduction...")
    debug_print(f"[Reduce] Combined answer token count (approx.): {token_count(combined)} tokens.")
    
    if token_count(combined) > context_size:
        print("[Reduce] Combined output exceeds context size. Splitting into intermediate chunks...")
        chunks = []
        current_chunk = ""
        for output in map_outputs:
            if token_count(current_chunk + "\n" + output) > context_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = output
            else:
                current_chunk = current_chunk + "\n" + output if current_chunk else output
        if current_chunk:
            chunks.append(current_chunk)
        
        print(f"[Reduce] Created {len(chunks)} intermediate chunks for further reduction.")
        debug_print(f"[Reduce] Reduced into {len(chunks)} intermediate chunks.")
        
        intermediate_results = []
        for i, chunk in enumerate(chunks, start=1):
            print(f"[Reduce] Reducing intermediate chunk {i} of {len(chunks)}...")
            prompt = (
                "Below are some partial answers produced by processing document chunks between the <partial_content> ... </partial_content> tags. "
                "Based solely on the text provided in these partial answers, please consolidate them into a single answer. "
                "Do not access external data. "
                "Be sure to keep and list all source file names mentioned in the content.\n\n"
                f"<partial_content>\n{chunk}\n</partial_content>\n\n"
                f"Intermediate question between <question> ... </question> tags: \n<question>\n{question}\n</question>\n\n"
                "Provide a consolidated answer including citations referencing the document sources (file names)."
            )
            debug_print(f"[Reduce] Processing intermediate chunk {i}/{len(chunks)} with token count (approx.): {token_count(chunk)}")
            intermediate_result = safe_invoke(prompt)
            intermediate_results.append(intermediate_result)
        return reduce_stage(intermediate_results, question, model, context_size)
    else:
        print("[Reduce] Combined output within context limit. Sending final prompt to model...")
        prompt = (
            "Below are the answers produced by processing document chunks between the <combined_content> ... </combined_content> tags. "
            "Based solely on the text provided in these answers, please consolidate them into a single final answer. "
            "Do not access external data. "
            "Be sure to keep and list all source file names mentioned in the content.\n\n"
            f"<combined_content>\n{combined}\n</combined_content>\n\n"
            f"Final question between <question> ... </question> tags: \n<question>\n{question}\n</question>\n\n"
            "Provide a consolidated final answer including citations referencing the document sources (file names)."
        )
        debug_print(f"[Reduce] Final prompt token count (approx.): {token_count(prompt)} tokens.")
        final_answer = safe_invoke(prompt)
        return final_answer

# --------------------------
# Main Pipeline
# --------------------------
def main():
    global DEBUG, chat_model

    parser_arg = argparse.ArgumentParser(
        description="Process complete documents as a knowledge base with Apache Tika and an LLM map-reduce pipeline."
    )
    parser_arg.add_argument("-d", "--directory", type=str, required=True,
                            help="Path to the directory containing files to process.")
    parser_arg.add_argument("-p", "--path", type=str, default=".*",
                            help="Regular expression(s) to match file paths. Separate multiple regexes with commas. (default: .*)")
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
    parser_arg.add_argument("-z", "--debug", action="store_true",
                            help="Enable debug output")
    args = parser_arg.parse_args()

    DEBUG = args.debug

    if args.query_file:
        query = args.query_file.read()
        args.query_file.close()
    elif args.query:
        query = args.query
    else:
        query = "Summarize the input context."

    model = args.model
    chunk_size = args.chunk_size
    chunk_overlap = args.chunk_overlap
    temperature = args.temperature
    num_ctx = args.num_ctx

    chat_model = ChatOllama(
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
        num_predict=-2,
        seed=3,
        keep_alive=-1
    )

    directory_path = args.directory
    regex_patterns = [re.compile(pattern.strip()) for pattern in args.path.split(',')]

    documents = crawl_directory_to_documents(directory_path, regex_patterns)
    debug_print(f"Total documents extracted: {len(documents)}")

    split_docs = split_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    debug_print(f"Total document chunks after splitting: {len(split_docs)}")

    map_outputs = map_stage(split_docs, query)
    if not map_outputs:
        print("No outputs from the map stage. Exiting.")
        return

    final_answer = reduce_stage(map_outputs, query, model=model, context_size=num_ctx)
    
    print("Final Answer:")
    print(final_answer)

    if args.output:
        try:
            with open(args.output, 'w') as outfile:
                outfile.write(final_answer)
            print(f"Final response written to {args.output}")
        except Exception as e:
            print(f"Error writing final response to {args.output}: {e}")

if __name__ == "__main__":
    main()
