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

combined_content = ""

files_to_read = [
    "js-route-builder.js",
    "relay-operations.js",
    "x-controllers.js"
]

# Read the files inside the folder
for fname in files_to_read:
    full_path = os.path.join(target_dir, fname)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            combined_content += f.read() + "\n"
    except FileNotFoundError:
        print(f"Warning: {fname} not found in {target_dir}, skipping.")

# Pattern for __d("function_name", payload)
pattern = re.compile(
    r'__d\("([^"]+)"\s*,(.*?)\);\s*',
    re.DOTALL
)

results = {}

# Process each line
for line in combined_content.splitlines():
    match = pattern.search(line)
    if not match:
        continue

    function_name = match.group(1).strip()
    payload = match.group(2).strip()

    # Hash payload
    hash_value = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # Save result
    results[function_name] = hash_value

# Write output JSON inside same folder
output_path = os.path.join(target_dir, "hashes.json")

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)

print(f"Extracted + hashed {len(results)} functions → {output_path}")
