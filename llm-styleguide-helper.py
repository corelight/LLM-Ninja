#!/usr/bin/env python3
"""
Vale Auto-Fix Prompt Generator

This script processes text files with Vale (a linting tool) and generates
prompts that can be used with AI models to automatically fix style guide
violations. It runs Vale on each .txt/.md/.fixed file, extracts the alerts/issues,
looks up relevant vocabulary definitions, and creates detailed prompts
for fixing the issues.

By default, the script only generates .prompt files. Use --gemini to enable
automatic fixing with Gemini CLI and iterative Vale validation.

Usage:
    python vale-gemini-styleguide.py --input-dir ./txt --styleguide-dir ./styleguide/a-z-word-list-term-collections
    python vale-gemini-styleguide.py --input-dir ./txt --styleguide-dir ./styleguide/a-z-word-list-term-collections --gemini
"""

import os
import json
import subprocess
import argparse
from pathlib import Path # Added for Path objects

# Define the directory where the script is run (assuming it's run from the project root)
# This BASE_DIR will be used for creating temporary files for Vale processing
BASE_DIR = Path(os.getcwd())

def run_vale_json(path, config_file: str = None):
    """
    Run Vale in JSON mode directly on the file (treated as Markdown).
    
    Args:
        path (str): Path to the file to analyze
        config_file (str, optional): Path to Vale configuration file
        
    Returns:
        dict: Parsed JSON output from Vale, or empty dict if parsing fails
    """
    # Execute Vale with JSON output format, treating file as markdown
    # Build the command with optional config parameter
    command = ["vale", "--output=JSON", "--ext=.md"]
    if config_file:
        command.extend(["--config", config_file])
    command.append(str(path))  # Add the file path at the end
    
    proc = subprocess.run(
        command,
        capture_output=True, text=True,
        cwd=BASE_DIR, # Ensure Vale runs in the correct directory to find .vale.ini
        env=os.environ # Pass current environment variables
    )
    
    # Parse Vale's JSON output
    try:
        return json.loads(proc.stdout or '{}')
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON from Vale for {path}:\n{proc.stdout}", flush=True)
        return {}

def extract_alerts(vale_json):
    """
    Flatten alerts whether JSON is mapping or list.
    
    Vale can return results in different formats:
    - As a dict mapping file paths to lists of alerts
    - As a direct list of alerts
    
    Args:
        vale_json (dict or list): Raw JSON output from Vale
        
    Returns:
        list: Flattened list of all alerts/issues found
    """
    alerts = []
    
    # Handle dict format (file path -> list of alerts)
    if isinstance(vale_json, dict):
        for v in vale_json.values():
            if isinstance(v, list):
                alerts.extend(v)
    # Handle direct list format
    elif isinstance(vale_json, list):
        alerts = vale_json
        
    return alerts

def get_vocab_definition(word, styleguide_dir):
    """
    Load the markdown file for a vocab word from the Microsoft Style Guide.
    
    The styleguide is organized alphabetically in directories (a/, b/, c/, etc.)
    with markdown files containing definitions for specific terms.
    
    Args:
        word (str): The vocabulary word to look up
        styleguide_dir (str): Path to the a-z-word-list-term-collections directory
        
    Returns:
        str or None: Content of the definition file, or None if not found
    """
    # Determine which letter directory to search in
    letter = word[0].lower()
    dir_path = os.path.join(styleguide_dir, letter)
    
    # Skip if the letter directory doesn't exist
    if not os.path.isdir(dir_path):
        return None
    
    # Search through all markdown files in the letter directory
    for fname in sorted(os.listdir(dir_path)):
        if not fname.lower().endswith('.md'):
            continue
            
        # Extract the base name and split on hyphens to get word parts
        name = fname[:-3]  # Remove .md extension
        parts = name.lower().split('-')
        
        # Check if our word matches any part of the filename
        if word.lower() in parts:
            try:
                return open(os.path.join(dir_path, fname), 'r').read().strip()
            except Exception:
                return None
                
    return None

def build_prompt(path, content, alerts, styleguide_dir):
    """
    Compose the Vale auto-fix prompt, including any vocab definitions.
    
    Creates a detailed prompt that can be used with AI models to automatically
    fix style guide violations found by Vale.
    
    Args:
        path (str): Path to the original file being processed
        content (str): Original content of the file
        alerts (list): List of Vale alerts/issues to fix
        styleguide_dir (str): Path to styleguide directory for vocab lookups
        
    Returns:
        str: Complete prompt text for AI model
    """
    # Convert alerts to formatted JSON for the prompt
    alerts_json = json.dumps(alerts, indent=2)
    
    # Look up definitions for any vocabulary-related alerts
    defs = []
    for a in alerts:
        # Check if this is a vocabulary alert (ends with .Vocab)
        if a.get('Check', '').endswith('.Vocab'):
            word = a.get('Match', '')
            definition = get_vocab_definition(word, styleguide_dir)
            defs.append((word, definition))
    
    # Build the definitions section if we found any vocab alerts
    def_section = ''
    if defs:
        def_section = '---\nA–Z definitions (use only for Vocab alerts):\n'
        for w, d in defs:
            if d:
                def_section += f"\n**{w}**:\n```\n{d}\n```\n"
            else:
                def_section += f"\n**{w}**: definition NOT found\n"

    # Construct the complete prompt with instructions and context
    return f"""Auto-fix this Markdown document (`{path}`) according to Vale's style guide.

--- Original content:
```markdown
{content}
```

You MUST follow these steps in order:
1. For each alert below, locate the sentence containing the issue.
2. Rewrite that sentence to resolve the alert (e.g., change passive-voice to active, swap vocab using definitions) without removing any concepts from the original text.
3. After all edits, output the entire corrected Markdown document with those sentences replaced.
⚠️ OUTPUT **only** the final Markdown content—no JSON, no explanations, no <think> ... </think>, no code fences.

--- Alerts (JSON):
```json
{alerts_json}
```

{def_section}"""

def run_gemini_cli(prompt_content: str, model: str = None) -> str:
    """
    Sends the prompt content to the gemini CLI and returns the fixed text.
    
    Args:
        prompt_content (str): The prompt to send to Gemini
        model (str, optional): The model to use (e.g., 'gemini-2.5-flash')
    """
    print("\n--- Sending prompt to Gemini CLI ---", flush=True)
    
    # Build the command with optional model parameter
    command = ["gemini", "-i"]
    if model:
        command.extend(["-m", model])
    
    try:
        # Use subprocess.Popen to pipe the prompt content to gemini's stdin
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=prompt_content)
        
        if process.returncode != 0:
            print(f"[ERROR] Gemini CLI exited with non-zero status {process.returncode}.", flush=True)
            print(f"Gemini CLI Stderr: {stderr}", flush=True)
            return "" # Return empty string on error
        
        # Filter out the unwanted line
        filtered_stdout_lines = [line for line in stdout.splitlines() if "Loaded cached credentials." not in line]
        filtered_stdout = "\n".join(filtered_stdout_lines)

        print("--- Received response from Gemini CLI ---", flush=True)
        return filtered_stdout.strip()
        
    except FileNotFoundError:
        print("Error: 'gemini' command not found. Please ensure the Gemini CLI is installed and in your system's PATH.", flush=True)
        return ""
    except Exception as e:
        print(f"An unexpected error occurred while running Gemini CLI: {e}", flush=True)
        return ""

def process_file_with_gemini(original_file_path, styleguide_dir, model: str = None, config_file: str = None):
    """
    Process a file with Gemini CLI and Vale in an iterative loop.
    
    Continues iterating until Vale output doesn't improve for 3 consecutive iterations,
    then moves on to the next file.
    
    Args:
        original_file_path (Path): Path to the original file
        styleguide_dir (str): Path to styleguide directory
        model (str, optional): The Gemini model to use
        config_file (str, optional): Path to Vale configuration file
        
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"\n--- Processing file with Gemini: {original_file_path.name} ---", flush=True)
    
    # Define paths for fixed and prompt files
    fixed_file_path = original_file_path.with_suffix('.txt.fixed') if original_file_path.suffix == '.txt' else original_file_path.with_suffix('.md.fixed')
    prompt_file_path = original_file_path.with_suffix('.txt.prompt') if original_file_path.suffix == '.txt' else original_file_path.with_suffix('.md.prompt')

    # Initialize content
    current_content = original_file_path.read_text()
    best_content = current_content
    
    # Track consecutive iterations without improvement
    no_improvement_count = 0
    MAX_NO_IMPROVEMENT = 3  # Stop after 3 iterations without improvement
    iteration = 0
    
    # Initialize best_alert_count as None to indicate we haven't run Vale yet
    best_alert_count = None

    while True:
        iteration += 1
        print(f"\nIteration {iteration} for {original_file_path.name}", flush=True)

        # Write current content to a temporary file for Vale to process
        # This is necessary because run_vale_json expects a file path
        temp_vale_input_path = BASE_DIR / f"temp_vale_input_{original_file_path.name}"
        temp_vale_input_path.write_text(current_content)

        # Run Vale on the current content (via temp file)
        vale_json = run_vale_json(temp_vale_input_path, config_file)
        alerts = extract_alerts(vale_json)
        current_alert_count = len(alerts)
        
        print(f"Current Vale alerts: {current_alert_count}", flush=True)

        # Clean up the temporary Vale input file
        if temp_vale_input_path.exists():
            temp_vale_input_path.unlink()

        # Check if we have improvement (skip on first iteration)
        if best_alert_count is not None:
            if current_alert_count < best_alert_count:
                best_alert_count = current_alert_count
                best_content = current_content
                no_improvement_count = 0  # Reset counter on improvement
                print(f"✓ Improvement! New best alert count: {best_alert_count}", flush=True)
            else:
                no_improvement_count += 1
                print(f"⚠ No improvement. Consecutive iterations without improvement: {no_improvement_count}", flush=True)
        else:
            # First iteration - just set the baseline
            best_alert_count = current_alert_count
            print(f"Baseline alert count: {best_alert_count}", flush=True)

        # Check stopping conditions
        if current_alert_count == 0:
            print("✓ No more Vale alerts. File is clean!", flush=True)
            break  # Exit loop if clean
        
        if no_improvement_count >= MAX_NO_IMPROVEMENT:
            print(f"⚠ Stopping after {MAX_NO_IMPROVEMENT} consecutive iterations without improvement.", flush=True)
            break

        # Generate prompt
        prompt = build_prompt(original_file_path.name, current_content, alerts, styleguide_dir)
        
        # Write prompt to .prompt file
        prompt_file_path.write_text(prompt)
        print(f"Prompt written to {prompt_file_path}", flush=True)

        # Get fixed text from Gemini CLI
        fixed_text = run_gemini_cli(prompt, model)
        
        if not fixed_text:
            print("✗ No fixed text received from Gemini CLI. Stopping iterations for this file.", flush=True)
            break

        current_content = fixed_text
        
        # Write current fixed content to .fixed file
        fixed_file_path.write_text(current_content)
        print(f"Fixed content written to {fixed_file_path}", flush=True)
    
    # After iterations, ensure the best content is saved
    if fixed_file_path.exists():
        if best_content != fixed_file_path.read_text(): # Only write if different
            fixed_file_path.write_text(best_content)
            print(f"Saved best fixed version to: {fixed_file_path}", flush=True)
        else:
            print(f"File {fixed_file_path.name} is already the best version.", flush=True)
    else:
        # If no .fixed file exists (e.g., file was already clean), just save the best content
        fixed_file_path.write_text(best_content)
        print(f"Saved best fixed version to: {fixed_file_path}", flush=True)

    # Clean up the prompt file
    if prompt_file_path.exists():
        prompt_file_path.unlink()
        print(f"Cleaned up {prompt_file_path}", flush=True)
    
    print(f"Completed {iteration} iterations for {original_file_path.name}. Final alert count: {best_alert_count}", flush=True)
    return True

def main():
    """
    Main function that orchestrates the entire process.
    
    Walks through the input directory, processes each .txt, .md, and .fixed file with Vale,
    and generates corresponding .prompt files for AI-based auto-fixing.
    If --gemini is specified, also runs the Gemini/Vale iteration process.
    """
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Generate and save Vale auto-fix prompts for .txt, .md, and .fixed files"
    )
    parser.add_argument("--input-dir", required=True,
                        help="Root directory to scan for .txt, .md, and .fixed files")
    parser.add_argument("--styleguide-dir", required=True,
                        help="Path to styleguide/a-z-word-list-term-collections")
    parser.add_argument("--gemini", action="store_true",
                        help="Enable Gemini CLI auto-fixing with iterative Vale validation")
    parser.add_argument("--model", 
                        help="Gemini model to use (e.g., 'gemini-2.5-flash'). If not specified, uses Gemini CLI default.")
    parser.add_argument("--vale-ini", 
                        help="Path to Vale configuration file (.vale.ini). If not specified, Vale uses its default configuration.")
    args = parser.parse_args()

    # Walk through all subdirectories looking for supported files
    for root, dirs, files in os.walk(args.input_dir):
        # Sort for consistent processing order
        dirs.sort(key=str.lower)
        files.sort(key=str.lower)
        
        # Process each supported file found
        for fname in files:
            # Only process original .txt or .md files, not .fixed or .prompt
            if not (fname.lower().endswith(".txt") or fname.lower().endswith(".md")):
                continue
            if fname.lower().endswith(".fixed") or fname.lower().endswith(".prompt"):
                continue
                
            # Get full path to the original file
            original_file_path = Path(os.path.join(root, fname))
            print(f"\n--- Processing file: {original_file_path.name} ---", flush=True)
            
            # Run Vale and extract alerts
            vale_json = run_vale_json(original_file_path, args.vale_ini)
            alerts = extract_alerts(vale_json)
            
            # Load the original file content
            content = original_file_path.read_text()
            
            # Build the auto-fix prompt
            prompt = build_prompt(original_file_path.name, content, alerts, args.styleguide_dir)
            
            # Save prompt next to original file with .prompt extension
            prompt_file_path = original_file_path.with_suffix('.txt.prompt') if original_file_path.suffix == '.txt' else original_file_path.with_suffix('.md.prompt')
            prompt_file_path.write_text(prompt)
            print(f"Prompt written to {prompt_file_path}", flush=True)
            
            # Run Gemini iteration if requested
            if args.gemini:
                success = process_file_with_gemini(original_file_path, args.styleguide_dir, args.model, args.vale_ini)
                if success:
                    print(f"✓ Gemini processing completed for {original_file_path.name}")
                else:
                    print(f"✗ Gemini processing failed for {original_file_path.name}")

    print("\nAll prompts generated.")
    if args.gemini:
        print("Gemini auto-fixing completed.")

# Execute main function when script is run directly
if __name__ == '__main__':
    main()