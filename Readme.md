# LLM-Ninja

<img src="images/logo.jpg" alt="Logo" width="300">

## Table of Contents
- [Overview](#overview)
- [Scripts](#scripts)
  - [map-reduce.py](#map-reducepy)
- [Getting Started](#getting-started)
- [Contributing](#contributing)
- [License](#license)

## Overview

LLM-Ninja is a collection of scripts and tools designed for working with large language models (LLMs). This repository provides modular solutions for document processing, map-reduce pipelines, and LLM integration, making it easier to build and experiment with LLM-powered applications.

LLM-Ninja is structured to support multiple scripts (more coming soon!). Each script is organized into its own section within this README, allowing you to understand the purpose, usage, and details for each script independently.

## Scripts

### map-reduce.py

This script demonstrates a complete map-reduce pipeline to process documents and query an LLM. It leverages Apache Tika for text extraction, LangChain for document splitting, ChatOllama for LLM integration, and LangGraph for managing workflow state.

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
  - `langgraph`
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
Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/README.md
Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/netsupport.sig
Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/main.zeek
Ingesting file: /Users/keith.jones/Source/zeek-netsupport-detector/scripts/__load__.zeek
File README.md produced 1 chunks.
File netsupport.sig produced 1 chunks.
File main.zeek produced 1 chunks.
File __load__.zeek produced 1 chunks.
[Map] Sending chunk from README.md (chunk 1/4) to the model...
[Map] Sending chunk from netsupport.sig (chunk 2/4) to the model...
[Map] Sending chunk from main.zeek (chunk 3/4) to the model...
[Map] Sending chunk from __load__.zeek (chunk 4/4) to the model...
[Reduce] Starting reduction stage...
[Reduce] Combining map outputs for reduction...
[Reduce] Combined output within context limit. Sending final prompt to model...
Final Answer:
The Zeek package detects NetSupport Command and Control (C2) traffic by analyzing network traffic captured in PCAP files for specific patterns associated with NetSupport malware activity. The detection process involves two primary mechanisms: HTTP headers analysis and command strings detection within TCP payloads.

1. **HTTP Headers Detection**:
   - The package identifies NetSupport C2 traffic by examining HTTP headers in the network packets. It looks for specific characteristics, such as "USER-AGENT" or "SERVER" headers containing the string "NetSupport". When these patterns are observed, a notice is triggered indicating NetSupport C2 activity via HTTP headers (`NetSupport::C2_Traffic_Observed_HTTP_Headers`). This detection mechanism is detailed in `main.zeek` (Global chunk 3 of 4).

2. **Command Strings Detection**:
   - The package detects specific command strings within TCP payloads, such as `CMD=POLL` and `CMD=ENCD`, which are indicative of NetSupport's C2 communications.
     - For the pattern `CMD=POLL`, a regular expression `/.*(\x0a|\x0d)CMD=POLL(\x0a|\x0d)/` is used to match occurrences bounded by newline characters. Detection triggers the function `NetSupport::netsupport_cmd_poll_match`.
     - Similarly, for `CMD=ENCD`, the pattern is matched using the regular expression `/.*(\x0a|\x0d)CMD=ENCD(\x0a|\x0d)/`. Upon detection, the function `NetSupport::netsupport_cmd_encd_match` is executed.
   - These signatures are part of a Zeek package designed to monitor and analyze network traffic for signs of NetSupport activity. The details about these signature match functions are provided in `netsupport.sig` (Global chunk 2 of 4).

The detection process is automated through Zeek scripts that parse the PCAP file and apply these rules to identify potential NetSupport activity. Logs generated include detailed information such as timestamps, source and destination IP addresses, ports, and specific notes on what was detected.

Citations:
- `README.md`
- `netsupport.sig` (Global chunk 2 of 4)
- `main.zeek` (Global chunk 3 of 4)
- `__load__.zeek` (Global chunk 4 of 4)
```

*Note: Installing and running Ollama, as well as downloading the default model (`phi4`), is required for the ChatOllama integration to work correctly.*

*Note: More scripts will be added in the future. Each script will have its own dedicated section in this README.*

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

## Contributing

Contributions are welcome! Feel free to fork the repository, submit pull requests, and open issues for improvements, bug fixes, or feature requests.

## License

This project is licensed under the following [LICENSE](LICENSE).
