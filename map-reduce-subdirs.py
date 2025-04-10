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
    parser.add_argument("-t", "--temperature", type=float, default=0.0,
                        help="Temperature for the ChatOllama model (default: 0.0).")
    parser.add_argument("-x", "--num_ctx", type=int, default=37500,
                        help="Context window size for ChatOllama (default: 37500).")
    parser.add_argument("-n", "--print_responses", action="store_true",
                        help="Output all LLM response as they happen.")
    parser.add_argument("-e", "--print_queries", action="store_true",
                        help="Show the full LLM queries (prompt text) in the output as they happen.")
    parser.add_argument("-l", "--log", action="store_true",
                        help="If provided, capture all output (including stderr) and save logs to map-reduce-subdirs.log in the current directory")
    parser.add_argument("-s", "--tika_server", type=str, default="http://localhost:9998",
                        help="The Tika server endpoint URL (default: http://localhost:9998).")
    parser.add_argument("-z", "--debug", action="store_true",
                        help="Enable debug output.")

    args = parser.parse_args()
    parent_dir = args.parent_directory

    # Prepare the additional options (everything except -d, -u, and -l).
    additional_options = []
    if args.path is not None:
        additional_options.extend(["-p", args.path])
    if args.query is not None:
        additional_options.extend(["-q", args.query])
    if args.query_file is not None:
        additional_options.extend(["-f", args.query_file])
    additional_options.extend(["-m", args.model])
    additional_options.extend(["-c", str(args.chunk_size)])
    additional_options.extend(["-o", str(args.chunk_overlap)])
    additional_options.extend(["-t", str(args.temperature)])
    additional_options.extend(["-x", str(args.num_ctx)])
    additional_options.extend(["-s", args.tika_server])
    if args.debug:
        additional_options.append("-z")
    if args.print_responses:
        additional_options.append("-n")
    if args.print_queries:
        additional_options.append("-e")
    
    # Log file for concatenated logs.
    concatenated_log_file = os.path.join(os.getcwd(), "map-reduce-subdirs.log")
    # If the log file exists and -l is provided, delete it before starting.
    if args.log and os.path.exists(concatenated_log_file):
        os.remove(concatenated_log_file)

    # Gather and sort first-level subdirectories (case-insensitive).
    subdirs = [item for item in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, item))]
    for item in sorted(subdirs, key=lambda s: s.lower()):
        subdir_path = os.path.join(parent_dir, item)
        # Save the output file in the current working directory.
        output_file = os.path.join(os.getcwd(), f"{item}.txt")
        if os.path.exists(output_file):
            print(f"Skipping directory: {subdir_path} (output already exists: {output_file})")
            continue

        print(f"Processing directory: {subdir_path}")

        # Build the command. Note: We do NOT pass the -l option to map-reduce.py.
        cmd = ["python", args.script, "-d", subdir_path, "-u", output_file]
        cmd.extend(additional_options)
        
        if args.log:
            # Append header for this subdirectory to the log file.
            with open(concatenated_log_file, "a") as logf:
                logf.write(f"===== Log for subdirectory: {subdir_path} =====\n")
            
            # Run the command, capturing all output (stdout and stderr).
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            # Open the log file once for the duration of this process, so we can write each line as it's produced.
            with open(concatenated_log_file, "a") as logf:
                for line in process.stdout:
                    sys.stdout.write(line)   # Print each line as it comes.
                    sys.stdout.flush()
                    logf.write(line)         # Write the same line to the log file.
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
