import json
import re
import urllib.parse
from datetime import datetime
from mitmproxy import http
import os

OUTPUT_FILE = "modules.json"

# Load existing modules file
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {"origins": {}}
else:
    data = {"origins": {}}


class ModuleExtractor:

    def request(self, flow: http.HTTPFlow):
        # Only target Facebook bootloader requests
        if "/ajax/bootloader-endpoint" not in flow.request.pretty_url:
            return

        req = flow.request
        url = req.pretty_url
        parsed = urllib.parse.urlparse(url)

        origin = f"{parsed.scheme}://{parsed.netloc}"

        # Ensure origin exists
        if origin not in data["origins"]:
            data["origins"][origin] = {}

        # Extract Referer path
        ref = req.headers.get("Referer")
        if not ref:
            return

        ref_parsed = urllib.parse.urlparse(ref)
        path = ref_parsed.path or "/"

        # Ensure path entry exists
        if path not in data["origins"][origin]:
            data["origins"][origin][path] = {
                "last_crawled": None,
                "parameters": {},
                "modules": {}
            }

        # Update crawl timestamp
        data["origins"][origin][path]["last_crawled"] = datetime.utcnow().isoformat() + "Z"

        # Parse query params
        query = urllib.parse.parse_qs(parsed.query)

        modules_raw = query.get("modules", [])
        if not modules_raw:
            return

        # Split modules correctly (comma-separated)
        modules_list = [
            m.strip()
            for m in modules_raw[0].split(",")
            if m.strip()
        ]

        modules_map = data["origins"][origin][path]["modules"]
        ts = datetime.utcnow().isoformat() + "Z"

        for module_name in modules_list:
            if module_name not in modules_map:
                modules_map[module_name] = {
                    "first_seen": ts,
                    "last_seen": ts
                }
            else:
                modules_map[module_name]["last_seen"] = ts

        # Store whitelisted params once at path level
        whitelist = ["__a", "__user", "fb_dtsg_ag", "__comet_req", "__crn"]
        remaining = {k: v[0] for k, v in query.items() if k in whitelist}
        data["origins"][origin][path]["parameters"] = remaining


        # Save immediately
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2)


addons = [ModuleExtractor()]
