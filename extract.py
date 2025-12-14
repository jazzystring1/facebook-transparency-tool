import json
import os
import re
import requests
import hashlib
import tldextract
from datetime import datetime
from urllib.parse import urlencode, urlparse

# -----------------------------
# Config
# -----------------------------

MODULES_JSON = "modules.json"
FUNCTIONS_JSON = "functions.json"
BOOTLOADERS_BASE = "bootloaders"
BOOTLOADER_REV = str(int(datetime.utcnow().timestamp()))

with open(".current-bootloader-snapshot", "w") as f:
    f.write(BOOTLOADER_REV)

JS_REGEX = re.compile(r"https://[^\s\"']+\.js")
FUNC_REGEX = re.compile(r'__d\("([^"]+)"')

SOURCE_PATTERNS = [
    r'document\.URL\b',
    r'document\.documentURI\b',
    r'document\.URLUnencoded\b',
    r'document\.baseURI\b',
    r'\blocation\b',
    r'document\.cookie\b',
    r'document\.referrer\b',
    r'window\.name\b',
    r'history\.pushState\s*\(',
    r'history\.replaceState\s*\(',
    r'localStorage\b',
    r'sessionStorage\b',
    r'(moz|webkit|ms)?IndexedDB\b',
    r'\bDatabase\b',
]

SINK_PATTERNS = [
    r'document\.write\s*\(',
    r'window\.location\b',
    r'document\.cookie\b',
    r'\beval\s*\(',
    r'document\.domain\b',
    r'WebSocket\s*\(',
    r'\.src\s*=',
    r'postMessage\s*\(',
    r'setRequestHeader\s*\(',
    r'FileReader\.readAsText\s*\(',
    r'ExecuteSql\s*\(',
    r'sessionStorage\.setItem\s*\(',
    r'document\.evaluate\s*\(',
    r'JSON\.parse\s*\(',
    r'\.setAttribute\s*\(',
    r'RegExp\s*\(',
]

# Human-readable mappings
SOURCE_MAP = {
    r'document\.URL\b': 'DocumentURL',
    r'document\.documentURI\b': 'DocumentURI',
    r'document\.URLUnencoded\b': 'DocumentURLUnencoded',
    r'document\.baseURI\b': 'DocumentBaseURI',
    r'\blocation\b': 'Location',
    r'document\.cookie\b': 'DocumentCookie',
    r'document\.referrer\b': 'DocumentReferrer',
    r'window\.name\b': 'WindowName',
    r'history\.pushState\s*\(': 'HistoryPushState',
    r'history\.replaceState\s*\(': 'HistoryReplaceState',
    r'localStorage\b': 'LocalStorage',
    r'sessionStorage\b': 'SessionStorage',
    r'(moz|webkit|ms)?IndexedDB\b': 'IndexedDB',
    r'\bDatabase\b': 'Database',
}

SINK_MAP = {
    r'document\.write\s*\(': 'DocumentWrite',
    r'window\.location\b': 'WindowLocation',
    r'document\.cookie\b': 'DocumentCookie',
    r'\beval\s*\(': 'Eval',
    r'document\.domain\b': 'DocumentDomain',
    r'WebSocket\s*\(': 'WebSocket',
    r'\.src\s*=': 'SetSrc',
    r'postMessage\s*\(': 'PostMessage',
    r'setRequestHeader\s*\(': 'SetRequestHeader',
    r'FileReader\.readAsText\s*\(': 'FileReaderReadAsText',
    r'ExecuteSql\s*\(': 'ExecuteSql',
    r'sessionStorage\.setItem\s*\(': 'SessionStorageSetItem',
    r'document\.evaluate\s*\(': 'DocumentEvaluate',
    r'JSON\.parse\s*\(': 'JSONParse',
    r'\.setAttribute\s*\(': 'SetAttribute',
    r'RegExp\s*\(': 'RegExp',
}

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
    origin = origin.strip()
    if not origin.startswith(("http://", "https://")):
        origin = "https://" + origin
    parsed = urlparse(origin)
    hostname = parsed.hostname or "unknown"
    ext = tldextract.extract(hostname)
    return ext.domain or hostname

def safe_js_filename(js_url: str) -> str:
    fname = js_url.split("/")[-1].split("?")[0]
    fname = re.sub(f"[{re.escape(INVALID_CHARS)}]", "_", fname)
    if len(fname) > MAX_FILENAME_LEN:
        h = hashlib.sha256(js_url.encode()).hexdigest()[:32]
        fname = f"{h}.js"
    return fname

def download_js(js_url: str, platform: str) -> str:
    folder = os.path.join(BOOTLOADERS_BASE, platform)
    platform_rev = os.path.join(folder, BOOTLOADER_REV)
    os.makedirs(platform_rev, exist_ok=True)
    filename = safe_js_filename(js_url)
    path = os.path.join(platform_rev, filename)
    if not os.path.exists(path):
        r = requests.get(js_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        with open(path, "w", encoding="utf-8") as f:
            f.write(r.text)
    return path

def extract_functions(js_path, platform_folder):
    """
    Extracts functions from a single-line JS file.
    Only returns functions with sources/sinks or special patterns.
    Writes function lines into others.js per platform **except** special patterns.
    Returns dict: function_name -> {"sources": [...], "sinks": [...]}
    """
    funcs = {}
    special_patterns = [
        r'jsRouteBuilder"\)\(',
        r'RelayOperation",\[',
        r'XController"\)\.cr'
    ]

    others_file = os.path.join(platform_folder, "others.js")
    with open(js_path, "r", encoding="utf-8") as f, open(others_file, "a", encoding="utf-8") as out_file:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = FUNC_REGEX.search(line)
            if not match:
                continue

            func_name = match.group(1)

            # Human-readable sources and sinks
            sources_found = [SOURCE_MAP[p] for p in SOURCE_PATTERNS if re.search(p, line)]
            sinks_found = [SINK_MAP[p] for p in SINK_PATTERNS if re.search(p, line)]

            # Special pattern check
            special_match = any(re.search(p, line) for p in special_patterns)

            if sources_found or sinks_found or special_match:
                funcs[func_name] = {
                    "sources": sources_found,
                    "sinks": sinks_found
                }
                # Only write to others.js if it's not a special pattern
                if not special_match:
                    out_file.write(line + "\n")

    return funcs


# -----------------------------
# Main
# -----------------------------

def main():
    modules_data = load_json(MODULES_JSON)
    functions_data = load_json(FUNCTIONS_JSON)

    visited_js = {}           # key = (platform, js_url) -> dict(function_name -> {...})
    requested_modules = set() # (origin, module)

    now = datetime.utcnow().isoformat() + "Z"

    for origin, origin_data in modules_data.get("origins", {}).items():
        base_url = origin.rstrip("/") if origin.startswith(("http://", "https://")) else f"https://{origin}"
        platform = platform_from_origin(origin)
        platform_folder = os.path.join(BOOTLOADERS_BASE, platform)
        os.makedirs(platform_folder, exist_ok=True)

        for path, path_data in origin_data.items():
            params = path_data.get("parameters", {})
            modules = path_data.get("modules", {})

            for module_name in modules.keys():
                dedup_key = (origin, module_name)
                if dedup_key in requested_modules:
                    continue
                requested_modules.add(dedup_key)

                print(f"[+] {platform} :: {module_name}")

                query = {"modules": module_name, **params}
                endpoint = f"{base_url}/ajax/bootloader-endpoint/?" + urlencode(query)

                try:
                    response = http_get(endpoint)
                except Exception as e:
                    print(f"[-] Bootloader failed: {e}")
                    continue

                js_urls = set(JS_REGEX.findall(response))

                for js_url in js_urls:
                    key = (platform, js_url)
                    try:
                        if key not in visited_js:
                            js_path = download_js(js_url, platform)
                            funcs = extract_functions(js_path, platform_folder)
                            visited_js[key] = funcs
                    except Exception as e:
                        print(f"[-] JS error: {js_url} ({e})")

                # Merge functions per module
                module_funcs = {}
                for key in [(platform, js) for js in js_urls]:
                    module_funcs.update(visited_js.get(key, {}))

                if module_name not in functions_data:
                    functions_data[module_name] = {
                        "first_seen": now,
                        "last_crawled": now,
                        "last_updated": now,
                        "functions": module_funcs
                    }
                else:
                    existing_funcs = functions_data[module_name].get("functions", {})
                    existing_funcs.update(module_funcs)
                    functions_data[module_name]["functions"] = existing_funcs
                    functions_data[module_name]["last_crawled"] = now
                    functions_data[module_name]["last_updated"] = now

    save_json(FUNCTIONS_JSON, functions_data)

if __name__ == "__main__":
    main()
