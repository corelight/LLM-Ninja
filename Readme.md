# LLM-Ninja

<img src="images/logo.jpg" alt="Logo" width="300">

## Table of Contents
- [Overview](#overview)
- [Scripts](#scripts)
  - [map-reduce.py](#map-reducepy)
  - [map-reduce-subdirs.py](#map-reduce-subdirspy)
  - [open-webui-knowledge.py](#open-webui-knowledgepy)
- [Getting Started](#getting-started)
- [Contributing](#contributing)
- [License](#license)

## Overview

LLM-Ninja is a collection of scripts and tools designed for working with large language models (LLMs). This repository provides modular solutions for document processing, map-reduce pipelines, and LLM integration, making it easier to build and experiment with LLM-powered applications.

LLM-Ninja is structured to support multiple scripts. Each script is organized into its own section within this README, allowing you to understand the purpose, usage, and details for each script independently.

## Scripts

### map-reduce.py

This script demonstrates a complete map-reduce pipeline to process documents and query an LLM. It leverages Apache Tika for text extraction, LangChain for document splitting, ChatOllama for LLM integration, and Ollama to serve the LLM model.

#### Features:
- **Document Ingestion:** Recursively traverses a directory to extract text from files using Apache Tika.
- **Text Splitting:** Divides extracted text into manageable chunks using LangChain's `RecursiveCharacterTextSplitter`.
- **Map Stage:** Sends each document chunk to the ChatOllama model along with a user-specified query to generate an answer.
- **Reduce Stage:** Consolidates individual responses into a final answer, handling context size limitations by recursively reducing intermediate results.
- **Citations:** Maintains citations referencing the document sources (file names) in the final output.

#### Prerequisites:
- **Python 3.7+**
- **Apache Tika Server:**  
  Download and start the Tika server manually. The script is configured to use the endpoint: `http://localhost:9998`.  
  More details: [Apache Tika Server](https://tika.apache.org/).
- **Required Python Packages:**
  - `tika`
  - `beautifulsoup4`
  - `langchain`
  - `langchain_ollama`
  - `argparse` (included in the standard library)
- **Ollama Installation and Model Download:**  
  To use the ChatOllama integration, you must install and run [Ollama](https://ollama.com/), and pull the required model (the default used here is `phi4`).

Install the dependencies:

```bash
pip install -r requirements.txt
```

#### Usage:
Run the script with the following command:
```bash
python map-reduce.py --directory /path/to/your/documents --query "Your query here"
```

##### Command-Line Arguments:
- `-d, --directory`: **(Required)** Directory containing files to process.
- `-p, --path`: Regular expression(s) to match file paths. Separate multiple regexes with commas (default: `.*`).
- `-q, --query`: A single query to ask the LLM. Overrides `--query_file` if both are provided.
- `-f, --query_file`: Path to a file containing a multi-line query.
- `-m, --model`: Specify the Ollama model (default: `phi4`).
- `-c, --chunk_size`: Chunk size for splitting documents (default: `100000`).
- `-o, --chunk_overlap`: Overlap between chunks (default: `100`).
- `-t, --temperature`: Temperature for the ChatOllama model (default: `0.0`).
- `-x, --num_ctx`: Context window size for ChatOllama (default: `37500`).
- `-u, --output`: If provided, write the final response to the specified file.
- `-s, --tika_server`: The Tika server endpoint URL (default: `http://localhost:9998`).
- `-z, --debug`: Enable debug output for detailed logs.

#### How It Works:
1. **Document Ingestion:**  
   The script recursively traverses the specified directory and extracts text from files using Apache Tika.
2. **Text Splitting:**  
   Extracted text is divided into manageable chunks using LangChain's `RecursiveCharacterTextSplitter`.
3. **Map Stage:**  
   Each chunk is processed by sending it to ChatOllama along with a prompt that includes the document content and the query.
4. **Reduce Stage:**  
   The map outputs are combined into a final answer. If the combined content exceeds the model's context size, the script recursively consolidates intermediate results.
5. **Final Output:**  
   The final consolidated answer, including citations referencing the document sources, is printed to the console.

#### Example:
Below is an example command and output for `map-reduce.py` for [Zeek's NetSupport Detector](https://github.com/corelight/zeek-netsupport-detector):

```bash
% python map-reduce.py -d ~/Source/zeek-netsupport-detector -q "How does this Zeek package detect NetSupport?." --path "(?i).*readme\.md,.*/scripts/.*\.(zeek|sig)"
```

Output:
```
2025-03-14 15:54:51 - INFO - Starting processing with directory: /Users/keith.jones/Source/zeek-netsupport-detector
2025-03-14 15:54:51 - INFO - Starting directory crawl: /Users/keith.jones/Source/zeek-netsupport-detector
2025-03-14 15:54:51 - INFO - Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/README.md
2025-03-14 15:54:51 - INFO - Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/netsupport.sig
2025-03-14 15:54:51 - INFO - Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/main.zeek
2025-03-14 15:54:51 - INFO - Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/__load__.zeek
2025-03-14 15:54:51 - INFO - Completed directory crawl. Total documents: 4
2025-03-14 15:54:51 - INFO - Starting document splitting with chunk size: 100,000 and overlap: 100
2025-03-14 15:54:51 - INFO - File README.md produced 1 chunk(s)
2025-03-14 15:54:51 - INFO - File netsupport.sig produced 1 chunk(s)
2025-03-14 15:54:51 - INFO - File main.zeek produced 1 chunk(s)
2025-03-14 15:54:51 - INFO - File __load__.zeek produced 1 chunk(s)
2025-03-14 15:54:51 - INFO - Document splitting complete. Total chunks: 4
2025-03-14 15:54:51 - INFO - Starting map stage with complete and multi-chunk files.
2025-03-14 15:54:51 - INFO - Starting map stage.
2025-03-14 15:54:51 - INFO - Created a complete file group with 4 file(s) (combined length: 4,551)
2025-03-14 15:54:51 - INFO - Processing complete file group 1/1 with 4 file(s)
2025-03-14 15:55:12 - INFO - HTTP Request: POST http://127.0.0.1:11434/api/chat "HTTP/1.1 200 OK"
2025-03-14 15:55:43 - INFO - Map stage complete. Total outputs: 1
2025-03-14 15:55:43 - INFO - Starting reduce stage with 1 map outputs.
2025-03-14 15:55:43 - INFO - Single map output detected. No reduction query needed.
Final Answer:
The Zeek package detects NetSupport by using a combination of signature-based detection and HTTP header analysis. Here's how it works:

 1. **Signature-Based Detection**:
    - The package defines two signatures in `netsupport.sig` to detect specific patterns associated with NetSupport Command and Control (C2) traffic.
      - **CMD=ENCD**: This signature looks for the pattern `CMD=ENCD` within TCP payloads (`ip-proto == tcp`). When this pattern is detected, it triggers a function `NetSupport::netsupport_cmd_encd_match`, which logs a notice indicating that NetSupport C2 activity has been observed. The payload containing the match is stored in the `sub` field of the notice.
      - **CMD=POLL**: Similarly, this signature detects the pattern `CMD=POLL` within TCP payloads. It triggers the function `NetSupport::netsupport_cmd_poll_match`, which logs a similar notice with details about the detection and stores the payload in the `sub` field.
 
    These signatures are loaded into Zeek using the `@load-sigs ./netsupport.sig` directive in `__load__.zeek`.
 
 2. **HTTP Header Analysis**:
    - The package also analyzes HTTP headers for indicators of NetSupport activity. In `main.zeek`, an event handler `http_header` is defined to inspect HTTP headers.
      - It specifically looks for the presence of "NetSupport" in either the "USER-AGENT" or "SERVER" headers.
      - If detected, it logs a notice indicating that NetSupport C2 activity has been observed via HTTP headers.
 
 These mechanisms together allow Zeek to detect and log potential NetSupport C2 traffic by identifying specific patterns and header information associated with this malware. The notices generated provide details about the detection, including timestamps, connection information, and relevant payloads.
 
 **Citations**:
 - Signature definitions: `netsupport.sig`
 - Event handler for HTTP headers: `main.zeek`
 - Loading of signatures: `__load__.zeek`
```

*Note: Installing and running Ollama, as well as downloading the default model (`phi4`), is required for the ChatOllama integration to work correctly.*

### map-reduce-subdirs.py

This script enables batch processing of multiple first-level subdirectories. It automatically locates `map-reduce.py` in the same directory as itself and saves the output files in the current working directory. If an output file for a subdirectory already exists, that subdirectory is skipped. The subdirectories are processed in case-insensitive order.

#### Command-Line Options:
- **parent_directory** (positional): Parent directory containing subdirectories to process.
- `--script`: Path to the processing script (default: `map-reduce.py` in the same directory as this script).
- `-p, --path`: Regular expression(s) to match file paths (default: `.*`).
- `-q, --query`: A single query to ask the LLM (overrides `--query_file` if provided).
- `-f, --query_file`: Path to a file containing a multi-line query.
- `-m, --model`: Specify the Ollama model (default: `phi4`).
- `-c, --chunk_size`: Chunk size for splitting documents (default: `100000`).
- `-o, --chunk_overlap`: Overlap between chunks (default: `100`).
- `-t, --temperature`: Temperature for the ChatOllama model (default: `0.0`).
- `-x, --num_ctx`: Context window size for ChatOllama (default: `37500`).
- `-s, --tika_server`: The Tika server endpoint URL (default: `http://localhost:9998`).
- `-z, --debug`: Enable debug output for detailed logs.

#### Usage Example:
```bash
python map-reduce-subdirs.py /path/to/parent_directory -q "Summarize the documents" -p ".*\.pdf"
```

This command processes each first-level subdirectory within `/path/to/parent_directory` using `map-reduce.py` for document processing and saves the output for each subdirectory in the current working directory as `<subdirectory_name>.txt`.

### open-webui-knowledge.py

This Python script ingests documents into [open-webui](https://github.com/open-webui/open-webui) for [knowledge based](https://docs.openwebui.com/features/workspace/knowledge/) LLM queries.

#### Prerequisites:
- **Python 3.7+**
- **Apache Tika Server:**  
  Download and start the Tika server manually. The script is configured to use the endpoint: `http://localhost:9998`.  
  More details: [Apache Tika Server](https://tika.apache.org/).
- **Required Python Packages:**
  - `Resquests`
- **Ollama Installation and Model Download:**  
  To use the ChatOllama integration, you must install and run [Ollama](https://ollama.com/), and pull the required model (the default used here is `phi4`).

Install the dependencies:

```bash
pip install -r requirements.txt
```

Before using this script, **you must install [open-webui](https://github.com/open-webui/open-webui)**. Then, follow these configuration steps in open-webui:

1. **Embedding Model:**  
   In the Admin Panel, navigate to **Settings -> Documents -> Embedding Model** and change it to `nomic-embed-text`.

   ![open-webui Document Ingestion](images/open-webui-settings-documents.png)

2. **Hybrid Search and Reranking:**  
   Enable hybrid search and set the reranking model to `BAAI/bge-reranker-v2-m3`.

3. **Content Extraction Engine:**  
   Switch the content extraction engine to **Tika** in the same settings page for improved document extraction. Be sure you install and run Tika first. More details: [Apache Tika Server](https://tika.apache.org/)

4. **Authentication Setup:**  
   - Disable authentication for `open-webui` by running:
     ```bash
     WEBUI_AUTH=False open-webui serve
     ```
   - Obtain your auth token by clicking the user icon in the upper right corner, selecting **Account**, and copying the token at the bottom of the screen.
     
   ![open-webui Token](images/open-webui-token.png)

#### Command-Line Arguments:
- `-k, --knowledge`: **(Required)** Specify the knowledge name.
- `-d, --directory`: **(Required)** Directory containing the documents to ingest.
- `-p, --pattern`: Regular expression(s) to filter files. Separate multiple patterns with commas.
- `-t, --token`: **(Required)** Auth token for open-webui.
- `-u, --url`: (Optional) Base URL for open-webui (default: `http://localhost:8080`).
- `--append`: (Optional) Toggle append mode. By default, append mode is OFF.

#### Example:
Below is an example command to ingest code and its output for [Zeek's NetSupport Detector](https://github.com/corelight/zeek-netsupport-detector):

```bash
% python open-webui-knowledge.py -k netsupport -d ~/Source/zeek-netsupport-detector -p "(?i).*readme\.md,.*/scripts/.*\.(zeek|sig)" -t your_auth_token_here
```

Output:
```
Using base URL: http://localhost:8080
Using knowledge name: netsupport
Using regex pattern(s): ['(?i).*readme\\.md', '.*/scripts/.*\\.(zeek|sig)']
Using directory: /Users/keith.jones/Source/zeek-netsupport-detector
Append mode is OFF
Knowledge 'netsupport' already exists with ID '87b098a2-6577-4618-9534-d559863e0e7b'. Deleting it...
Deleted knowledge with ID '87b098a2-6577-4618-9534-d559863e0e7b'.
Created new knowledge 'netsupport' with ID 'b2b90141-28ac-4a82-be03-d0a8877768c1'.
Processing file 1: /Users/keith.jones/Source/zeek-netsupport-detector/README.md
Added file ID '7f8ab9ff-9c57-407b-9acb-4e4e729dcc3a' to knowledge 'b2b90141-28ac-4a82-be03-d0a8877768c1'.
Processing file 2: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/netsupport.sig
Added file ID '4b753bc0-a345-4f66-b394-c4c30816ee90' to knowledge 'b2b90141-28ac-4a82-be03-d0a8877768c1'.
Processing file 3: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/main.zeek
Added file ID '0b528600-3fb0-4c21-a70f-8307b9aad959' to knowledge 'b2b90141-28ac-4a82-be03-d0a8877768c1'.
Processing file 4: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/__load__.zeek
Added file ID 'a947f039-14bc-4d94-9908-41682b1e147b' to knowledge 'b2b90141-28ac-4a82-be03-d0a8877768c1'.
```

If you open Workspace and go to Knowledge, you will see your new knowledge base called `netsupport`:

![open-webui Knowledge](images/open-webui-knowledge-netsupport-1.png)
![open-webui NetSupport Knowledge](images/open-webui-knowledge-netsupport-2.png)

You can then type `#netsupport` in a chat prompt and click on the new collection for an example query to an LLM:

![open-webui NetSupport Knowledge Response](images/open-webui-knowledge-netsupport-3.png)

## Getting Started

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your_username/LLM-Ninja.git
   cd LLM-Ninja
   ```

2. **Set up a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. Now follow the instructions for the script above you would like to run.

## Contributing

Contributions are welcome! Feel free to fork the repository, submit pull requests, and open issues for improvements, bug fixes, or feature requests.

## License

This project is licensed under the following [LICENSE](LICENSE).