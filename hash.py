import re
import json
import hashlib
import sys
import os

# Accept folder argument
if len(sys.argv) > 1:
    target_dir = sys.argv[1]
else:
    target_dir = "."

# Normalize path
target_dir = os.path.abspath(target_dir)
print(f"Processing folder: {target_dir}")

files_to_read = [
    "js-route-builder.js",
    "relay-operations.js",
    "x-controllers.js",
    "others.js"  # New file with multi-line functions
]

results = {}

# Helper: process single-line JS files
def process_single_line_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Warning: {os.path.basename(file_path)} not found, skipping.")
        return {}

    pattern = re.compile(r'__d\("([^"]+)"\s*,(.*?)\);\s*', re.DOTALL)
    file_results = {}
    for line in content.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        func_name = match.group(1).strip()
        payload = match.group(2).strip()
        hash_value = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        file_results[func_name] = hash_value
    return file_results

# Helper: process others.js with multi-line functions
def process_others_js(file_path):
    file_results = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current_func_name = None
            current_func_lines = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('__d("'):  # New function start
                    # Hash previous function
                    if current_func_name and current_func_lines:
                        block = "\n".join(current_func_lines)
                        h = hashlib.sha256(block.encode("utf-8")).hexdigest()
                        file_results[current_func_name] = h
                    # Start new function
                    parts = line.split('"', 2)
                    if len(parts) >= 2:
                        current_func_name = parts[1]
                        current_func_lines = [line]
                    else:
                        current_func_name = None
                        current_func_lines = []
                else:
                    # Continue function body
                    if current_func_name:
                        current_func_lines.append(line)
            # Hash last function
            if current_func_name and current_func_lines:
                block = "\n".join(current_func_lines)
                h = hashlib.sha256(block.encode("utf-8")).hexdigest()
                file_results[current_func_name] = h
    except FileNotFoundError:
        print(f"Warning: others.js not found, skipping.")
    return file_results

# Process each file
for fname in files_to_read:
    full_path = os.path.join(target_dir, fname)
    if fname == "others.js":
        results.update(process_others_js(full_path))
    else:
        results.update(process_single_line_file(full_path))

# Write output JSON inside same folder
output_path = os.path.join(target_dir, "hashes.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print(f"Extracted + hashed {len(results)} functions → {output_path}")
