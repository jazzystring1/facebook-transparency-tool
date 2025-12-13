import json
import os
import re
import requests
import hashlib
from datetime import datetime
from urllib.parse import urlencode

# -----------------------------
# Config
# -----------------------------

MODULES_JSON = "modules.json"
FUNCTIONS_JSON = "functions.json"
BOOTLOADERS_BASE = "bootloaders"

JS_REGEX = re.compile(r"https://[^\s\"']+\.js")
FUNC_REGEX = re.compile(r'__d\("([^"]+)"')

MAX_FILENAME_LEN = 200
INVALID_CHARS = r'<>:"/\\|?*'

REQUEST_TIMEOUT = 30

# -----------------------------
# Helpers
# -----------------------------

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def http_get(url):
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def platform_from_origin(origin: str) -> str:
    """
    Returns the main domain name without subdomains or TLD.
    Examples:
        https://business.facebook.com -> facebook
        www.instagram.com -> instagram
        www.test.domain.co.uk -> domain
    """
    origin = origin.strip()

    # Add scheme if missing
    if not origin.startswith("http://") and not origin.startswith("https://"):
        origin = "https://" + origin

    parsed = urlparse(origin)
    hostname = parsed.hostname or "unknown"

    # Extract domain using tldextract
    ext = tldextract.extract(hostname)
    return ext.domain or hostname

def safe_js_filename(js_url: str) -> str:
    """
    Returns a safe filename for a JS URL.
    - Use original filename if short and valid
    - Otherwise, hash the URL
    """
    # Extract base filename from URL (strip query string)
    fname = js_url.split("/")[-1].split("?")[0]

    # Remove invalid characters
    fname = re.sub(f"[{re.escape(INVALID_CHARS)}]", "_", fname)

    # Hash if too long
    if len(fname) > MAX_FILENAME_LEN:
        h = hashlib.sha256(js_url.encode()).hexdigest()[:32]
        fname = f"{h}.js"

    return fname


def download_js(js_url: str, hostname: str) -> str:
    """
    Downloads the JS file into bootloaders/{hostname}/.
    Returns the full path to the downloaded file.
    Skips download if file already exists.
    """
    folder = os.path.join(BOOTLOADERS_BASE, hostname)
    os.makedirs(folder, exist_ok=True)

    filename = safe_js_filename(js_url)
    path = os.path.join(folder, filename)

    if not os.path.exists(path):
        import requests
        r = requests.get(js_url, timeout=30)
        r.raise_for_status()
        with open(path, "w", encoding="utf-8") as f:
            f.write(r.text)

    return path


def extract_functions(js_path):
    funcs = set()
    with open(js_path, "r", encoding="utf-8") as f:
        for line in f:
            for name in FUNC_REGEX.findall(line):
                funcs.add(name)
    return funcs


# -----------------------------
# Main
# -----------------------------

def main():
    modules_data = load_json(MODULES_JSON)
    functions_data = load_json(FUNCTIONS_JSON)

    visited_js = {}                  # js_url -> set(functions)
    requested_modules = set()        # (origin, module)

    now = datetime.utcnow().isoformat() + "Z"

    for origin, origin_data in modules_data.get("origins", {}).items():

        # Normalize base URL
        if origin.startswith("http://") or origin.startswith("https://"):
            base_url = origin.rstrip("/")
        else:
            base_url = f"https://{origin}"

        platform = platform_from_origin(origin)

        for path, path_data in origin_data.items():
            params = path_data.get("parameters", {})
            modules = path_data.get("modules", {})

            for module_name in modules.keys():

                dedup_key = (origin, module_name)
                if dedup_key in requested_modules:
                    continue

                requested_modules.add(dedup_key)

                print(f"[+] {platform} :: {module_name}")

                query = {
                    "modules": module_name,
                    **params
                }

                endpoint = (
                    f"{base_url}/ajax/bootloader-endpoint/?"
                    + urlencode(query)
                )

                try:
                    response = http_get(endpoint)
                except Exception as e:
                    print(f"[-] Bootloader failed: {e}")
                    continue

                js_urls = set(JS_REGEX.findall(response))
                module_functions = set()

                for js_url in js_urls:
                    try:
                        if js_url in visited_js:
                            module_functions |= visited_js[js_url]
                        else:
                            js_path = download_js(js_url, platform)
                            funcs = extract_functions(js_path)
                            visited_js[js_url] = funcs
                            module_functions |= funcs
                    except Exception as e:
                        print(f"[-] JS error: {js_url} ({e})")

                if module_name not in functions_data:
                    functions_data[module_name] = {
                        "first_seen": now,
                        "last_crawled": now,
                        "last_updated": now,
                        "functions": sorted(module_functions)
                    }
                else:
                    existing = set(functions_data[module_name]["functions"])
                    merged = existing | module_functions

                    functions_data[module_name]["functions"] = sorted(merged)
                    functions_data[module_name]["last_crawled"] = now
                    functions_data[module_name]["last_updated"] = now

    save_json(FUNCTIONS_JSON, functions_data)


if __name__ == "__main__":
    main()
