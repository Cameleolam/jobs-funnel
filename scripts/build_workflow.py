#!/usr/bin/env python3
"""Build workflow_v2.json by inlining JS files into the template.

Usage:
    python scripts/build_workflow.py

Reads workflow_v2_template.json, replaces {{file:scripts/n8n/xxx.js}} placeholders
with the file contents (escaped for JSON string), writes workflow_v2.json.
"""

import json
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT_DIR / "workflow_v2_template.json"
OUTPUT = PROJECT_DIR / "workflow_v2.json"


def js_to_json_string(js_path: Path) -> str:
    """Read a JS file and escape it for embedding in a JSON string value."""
    content = js_path.read_text(encoding="utf-8").strip()
    # JSON string escaping: backslash, quotes, newlines, tabs
    content = content.replace("\\", "\\\\")
    content = content.replace('"', '\\"')
    content = content.replace("\n", "\\n")
    content = content.replace("\t", "\\t")
    content = content.replace("\r", "")
    return content


def build():
    if not TEMPLATE.exists():
        print(f"Error: {TEMPLATE} not found")
        return 1

    template_text = TEMPLATE.read_text(encoding="utf-8")

    # Find all {{file:path}} placeholders
    pattern = re.compile(r'\{\{file:(scripts/n8n/[^}]+)\}\}')

    def replacer(match):
        rel_path = match.group(1)
        js_file = PROJECT_DIR / rel_path
        if not js_file.exists():
            print(f"Warning: {js_file} not found, skipping")
            return match.group(0)
        escaped = js_to_json_string(js_file)
        print(f"  Inlined {rel_path} ({len(escaped)} chars)")
        return escaped

    result = pattern.sub(replacer, template_text)

    # Validate JSON
    try:
        json.loads(result)
    except json.JSONDecodeError as e:
        print(f"Error: Output is not valid JSON: {e}")
        return 1

    OUTPUT.write_text(result, encoding="utf-8")
    print(f"\nBuilt {OUTPUT.name} successfully")
    return 0


if __name__ == "__main__":
    exit(build())
