import os
import json
import sys

def load_hashes(path):
    file_path = os.path.join(path, "hashes.json")
    if not os.path.exists(file_path):
        print(f"[ERROR] hashes.json not found in: {path}")
        sys.exit(1)
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"[ERROR] hashes.json is corrupted in: {path}")
            sys.exit(1)
            return {}


def main():
    if len(sys.argv) != 3:
        print("Usage: python diff.py <source_folder> <compare_folder>")
        print("Example: python diff.py facebook-1 facebook-2")
        sys.exit(1)

    source_folder = sys.argv[1]
    compare_folder = sys.argv[2]

    print(f"\n[+] Loading SOURCE folder (truth): {source_folder}")
    source_hashes = load_hashes(source_folder)

    print(f"[+] Loading COMPARE folder: {compare_folder}")
    new_hashes = load_hashes(compare_folder)

    if not source_hashes or not new_hashes:
        print("[WARN] Nothing to diff because hashes.json is empty")
        sys.exit(0)

    # Compute differences
    added = {}
    removed = {}
    modified = {}

    # Check for removed or modified functions
    for func, old_hash in source_hashes.items():
        if func not in new_hashes:
            removed[func] = old_hash
        else:
            if new_hashes[func] != old_hash:
                modified[func] = {
                    "old": old_hash,
                    "new": new_hashes[func]
                }

    # Check for added functions
    for func, new_hash in new_hashes.items():
        if func not in source_hashes:
            added[func] = new_hash

    # Prepare output object
    output_data = {
        "added": added,
        "removed": removed,
        "modified": modified
    }

    # Write output JS
    with open("output.js", "w", encoding="utf-8") as f:
        f.write("module.exports = ")
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        f.write(";\n")

    print("\n===== DIFF COMPLETE =====")
    print(f"Added: {len(added)}")
    print(f"Removed: {len(removed)}")
    print(f"Modified: {len(modified)}")
    print("→ Output written to output.js\n")


if __name__ == "__main__":
    main()
