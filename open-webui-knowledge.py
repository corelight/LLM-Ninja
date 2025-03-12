#!/usr/bin/env python3
import argparse
import os
import re
import requests
import sys

def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def list_knowledge(base_url, token):
    url = f"{base_url}/api/v1/knowledge/list"
    try:
        r = requests.get(url, headers=get_headers(token))
        if r.status_code == 200:
            return r.json()
        else:
            print(f"Error listing knowledge (status {r.status_code}).")
            sys.exit(1)
    except Exception as e:
        print(f"Error listing knowledge: {e}")
        sys.exit(1)

def find_knowledge_by_name(base_url, token, knowledge_name):
    knowledge_list = list_knowledge(base_url, token)
    for kn in knowledge_list:
        if kn.get("name") == knowledge_name:
            return kn
    return None

def delete_knowledge(base_url, knowledge_id, token):
    url = f"{base_url}/api/v1/knowledge/{knowledge_id}/delete"
    try:
        r = requests.delete(url, headers=get_headers(token))
        if r.status_code == 200:
            print(f"Deleted knowledge with ID '{knowledge_id}'.")
        else:
            print(f"Warning: Could not delete knowledge ID '{knowledge_id}' (status {r.status_code}).")
    except Exception as e:
        print(f"Error deleting knowledge ID '{knowledge_id}': {e}")
        sys.exit(1)

def create_knowledge(base_url, knowledge_name, token):
    url = f"{base_url}/api/v1/knowledge/create"
    payload = {"name": knowledge_name, "description": ""}
    try:
        r = requests.post(url, json=payload, headers=get_headers(token))
        if r.status_code == 200:
            data = r.json()
            print(f"Created new knowledge '{knowledge_name}' with ID '{data['id']}'.")
            return data
        else:
            print(f"Error creating knowledge '{knowledge_name}' (status {r.status_code}).")
            sys.exit(1)
    except Exception as e:
        print(f"Error creating knowledge '{knowledge_name}': {e}")
        sys.exit(1)

def upload_file(base_url, token, file_path):
    url = f"{base_url}/api/v1/files/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            r = requests.post(url, headers=headers, files=files)
        if r.status_code == 200:
            data = r.json()
            file_id = data.get("id")
            if not file_id:
                print(f"Upload succeeded but no file ID returned for {file_path}.")
                return None
            return file_id
        else:
            print(f"Error uploading file {file_path} (status {r.status_code}).")
            return None
    except Exception as e:
        print(f"Error uploading file {file_path}: {e}")
        return None

def add_file_id_to_knowledge(base_url, token, knowledge_id, file_id):
    url = f"{base_url}/api/v1/knowledge/{knowledge_id}/file/add"
    payload = {"file_id": file_id}
    try:
        r = requests.post(url, json=payload, headers=get_headers(token))
        if r.status_code == 200:
            print(f"Added file ID '{file_id}' to knowledge '{knowledge_id}'.")
        else:
            print(f"Error adding file ID {file_id} to knowledge {knowledge_id} (status {r.status_code}).")
    except Exception as e:
        print(f"Error adding file ID {file_id} to knowledge {knowledge_id}: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Recursively crawl a directory and add files to an Open-WebUI knowledge."
    )
    parser.add_argument("-k", "--knowledge", required=True, help="Name of the knowledge to create/use")
    parser.add_argument("-p", "--path", default=".*", help="Regular expression(s) to match the entire file path. "
                                                            "Separate multiple regexes with commas.")
    parser.add_argument("-d", "--directory", required=True, help="Directory to crawl for files")
    parser.add_argument("-b", "--base-url", default="http://localhost:8080", help="Base URL for the Open-WebUI API")
    parser.add_argument("-t", "--token", required=True, help="Bearer token for API authorization")
    parser.add_argument("-a", "--append", action="store_true", help="Append to existing knowledge (do not delete)")
    args = parser.parse_args()

    knowledge_name = args.knowledge
    # Compile regex patterns from the comma-separated string
    regex_patterns = [re.compile(pattern.strip()) for pattern in args.path.split(',')]
    base_url = args.base_url
    token = args.token

    print(f"Using base URL: {base_url}")
    print(f"Using knowledge name: {knowledge_name}")
    print(f"Using regex pattern(s): {[pattern.pattern for pattern in regex_patterns]}")
    print(f"Using directory: {args.directory}")
    print(f"Append mode is {'ON' if args.append else 'OFF'}")

    # Check if the knowledge already exists
    existing_knowledge = find_knowledge_by_name(base_url, token, knowledge_name)
    if existing_knowledge:
        knowledge_id = existing_knowledge["id"]
        if args.append:
            print(f"Appending to existing knowledge '{knowledge_name}' with ID '{knowledge_id}'.")
        else:
            print(f"Knowledge '{knowledge_name}' already exists with ID '{knowledge_id}'. Deleting it...")
            delete_knowledge(base_url, knowledge_id, token)
            created_kn = create_knowledge(base_url, knowledge_name, token)
            knowledge_id = created_kn["id"]
    else:
        created_kn = create_knowledge(base_url, knowledge_name, token)
        knowledge_id = created_kn["id"]

    # Counter for files processed
    file_counter = 0

    # Walk the directory and handle each file using regex matching on the full file path.
    for root, dirs, files in os.walk(args.directory):
        for file in files:
            file_path = os.path.join(root, file)
            if any(regex.search(file_path) for regex in regex_patterns):
                file_counter += 1
                print(f"Processing file {file_counter}: {file_path}")
                file_id = upload_file(base_url, token, file_path)
                if file_id:
                    add_file_id_to_knowledge(base_url, token, knowledge_id, file_id)

if __name__ == "__main__":
    main()
