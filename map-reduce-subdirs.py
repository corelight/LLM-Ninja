#!/usr/bin/env python3
import os
import subprocess
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Run map-reduce.py on each first-level subdirectory, passing all supported options, and save output to subdirectoryname.txt in the current directory."
    )
    parser.add_argument("parent_directory", help="Parent directory containing subdirectories to process.")
    # Determine the default processing script (map-reduce.py) in the same directory as this script.
    script_default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map-reduce.py")
    parser.add_argument(
        "--script",
        default=script_default,
        help="Path to the processing script (default: map-reduce.py in the same directory as this script)."
    )
    # Options that will be passed to the processing script.
    # Note: -d (directory) and -u (output) are handled by this wrapper.
    parser.add_argument("-p", "--path", type=str, default=".*",
                        help="Regex pattern(s) to match file paths. (default: .*)")
    parser.add_argument("-q", "--query", type=str,
                        help="A single query to ask the LLM (overrides --query_file if provided).")
    parser.add_argument("-f", "--query_file", type=str,
                        help="Path to a file containing the multi-line query.")
    parser.add_argument("-m", "--model", type=str, default="phi4",
                        help="The Ollama model used for the queries (default: phi4).")
    parser.add_argument("-c", "--chunk_size", type=int, default=65000,
                        help="Chunk size for splitting the documents (default: 65000).")
    parser.add_argument("-o", "--chunk_overlap", type=int, default=0,
                        help="Chunk overlap for splitting the documents (default: 0).")
    parser.add_argument("-t", "--temperature", type=float, default=None,
                        help="Temperature for the ChatOllama model (if omitted, use the model's default).")
    parser.add_argument("-x", "--num_ctx", type=int, default=None,
                        help="Context window size for ChatOllama (if omitted, use the model's default).")
    parser.add_argument("-K", "--top_k", type=int, default=None,
                        help="Top-k sampling cutoff for ChatOllama (if omitted, use default).")
    parser.add_argument("-P", "--top_p", type=float, default=None,
                        help="Top-p (nucleus) sampling for ChatOllama (if omitted, use default).")
    parser.add_argument("-g", "--num_predict", type=int, default=None,
                        help="Number of tokens to predict for ChatOllama (if omitted, use default).")
    parser.add_argument("-n", "--print_responses", action="store_true",
                        help="Output all LLM responses as they happen.")
    parser.add_argument("-e", "--print_queries", action="store_true",
                        help="Show the full LLM queries (prompt text) in the output as they happen.")
    parser.add_argument("-l", "--log", action="store_true",
                        help="If provided, capture all output (including stderr) and save logs to map-reduce-subdirs.log in the current directory.")
    parser.add_argument("-s", "--tika_server", type=str, default="http://localhost:9998",
                        help="The Tika server endpoint URL (default: http://localhost:9998).")
    parser.add_argument("-z", "--debug", action="store_true",
                        help="Enable debug output.")

    args = parser.parse_args()
    parent_dir = args.parent_directory

    # Prepare the additional options (everything except -d, -u, and -l).
    additional_options = []
    if args.path is not None:
        additional_options += ["-p", args.path]
    if args.query is not None:
        additional_options += ["-q", args.query]
    if args.query_file is not None:
        additional_options += ["-f", args.query_file]
    additional_options += ["-m", args.model]
    additional_options += ["-c", str(args.chunk_size)]
    additional_options += ["-o", str(args.chunk_overlap)]
    if args.temperature is not None:
        additional_options += ["-t", str(args.temperature)]
    if args.num_ctx is not None:
        additional_options += ["-x", str(args.num_ctx)]
    if args.top_k is not None:
        additional_options += ["-K", str(args.top_k)]
    if args.top_p is not None:
        additional_options += ["-P", str(args.top_p)]
    if args.num_predict is not None:
        additional_options += ["-g", str(args.num_predict)]
    additional_options += ["-s", args.tika_server]
    if args.debug:
        additional_options.append("-z")
    if args.print_responses:
        additional_options.append("-n")
    if args.print_queries:
        additional_options.append("-e")

    # Log file for concatenated logs.
    concatenated_log_file = os.path.join(os.getcwd(), "map-reduce-subdirs.log")
    if args.log and os.path.exists(concatenated_log_file):
        os.remove(concatenated_log_file)

    # Gather and sort first-level subdirectories (case-insensitive).
    subdirs = [item for item in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, item))]
    for item in sorted(subdirs, key=lambda s: s.lower()):
        subdir_path = os.path.join(parent_dir, item)
        output_file = os.path.join(os.getcwd(), f"{item}.txt")
        if os.path.exists(output_file):
            print(f"Skipping directory: {subdir_path} (output already exists: {output_file})")
            continue

        print(f"Processing directory: {subdir_path}")
        # Build the command. Note: We do NOT pass the -l option to map-reduce.py.
        cmd = ["python", args.script, "-d", subdir_path, "-u", output_file] + additional_options

        if args.log:
            # Append header for this subdirectory to the log file.
            with open(concatenated_log_file, "a") as logf:
                logf.write(f"===== Log for subdirectory: {subdir_path} =====")
            # Run the command, capturing all output.
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with open(concatenated_log_file, "a") as logf:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    logf.write(line)
                    logf.flush()
            process.wait()
            # Append a separator after the output.
            with open(concatenated_log_file, "a") as logf:
                logf.write("\n========================================\n\n")
            print(f"Output saved to: {output_file}")
            print(f"Logs appended to: {concatenated_log_file}")
        else:
            subprocess.run(cmd, check=True)
            print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    main()
