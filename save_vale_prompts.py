#!/usr/bin/env python3
"""
Vale Auto-Fix Prompt Generator

This script processes text files with Vale (a linting tool) and generates
prompts that can be used with AI models to automatically fix style guide
violations. It runs Vale on each .txt/.md/.fixed file, extracts the alerts/issues,
looks up relevant vocabulary definitions, and creates detailed prompts
for fixing the issues.

Usage:
    python save_vale_prompts.py --input-dir ./txt --styleguide-dir ./styleguide/a-z-word-list-term-collections
"""

import os
import json
import subprocess
import argparse

def run_vale_json(path):
    """
    Run Vale in JSON mode directly on the file (treated as Markdown).
    
    Args:
        path (str): Path to the file to analyze
        
    Returns:
        dict: Parsed JSON output from Vale, or empty dict if parsing fails
    """
    # Execute Vale with JSON output format, treating file as markdown
    proc = subprocess.run(
        ["vale", "--output=JSON", "--ext=.md", path],
        capture_output=True, text=True
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

def main():
    """
    Main function that orchestrates the entire process.
    
    Walks through the input directory, processes each .txt, .md, and .fixed file with Vale,
    and generates corresponding .prompt files for AI-based auto-fixing.
    """
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Generate and save Vale auto-fix prompts for .txt, .md, and .fixed files"
    )
    parser.add_argument("--input-dir", required=True,
                        help="Root directory to scan for .txt, .md, and .fixed files")
    parser.add_argument("--styleguide-dir", required=True,
                        help="Path to styleguide/a-z-word-list-term-collections")
    args = parser.parse_args()

    # Walk through all subdirectories looking for supported files
    for root, dirs, files in os.walk(args.input_dir):
        # Sort for consistent processing order
        dirs.sort(key=str.lower)
        files.sort(key=str.lower)
        
        # Process each supported file found
        for fname in files:
            if not (fname.lower().endswith(".txt") or 
                   fname.lower().endswith(".md") or 
                   fname.lower().endswith(".fixed")):
                continue
                
            # Get full path to the original file
            orig = os.path.join(root, fname)
            print(f"Processing {orig}")
            
            # Run Vale and extract alerts
            vale_json = run_vale_json(orig)
            alerts = extract_alerts(vale_json)
            
            # Load the original file content
            content = open(orig, 'r').read()
            
            # Build the auto-fix prompt
            prompt = build_prompt(orig, content, alerts, args.styleguide_dir)
            
            # Save prompt next to original file with .prompt extension
            prompt_path = orig + ".prompt"
            with open(prompt_path, 'w') as out:
                out.write(prompt)
            print(f"Prompt written to {prompt_path}\n")

    print("All prompts generated.")

# Execute main function when script is run directly
if __name__ == '__main__':
    main()
