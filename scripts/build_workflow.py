#!/usr/bin/env python3
"""Build workflow.json by inlining JS files + crawler registry into the template.

Usage:
    JOBS_FUNNEL_PROFILE=profile1 python scripts/build_workflow.py

Reads:
    - workflow_template.json (placeholders: {{file:...}}, {{crawler_nodes}},
      {{crawler_connections}}, {{crawler_count}})
    - profiles/$JOBS_FUNNEL_PROFILE/search.json (for the crawlers[] list)
    - scripts/n8n/crawlers.json (registry)

Writes: workflow.json
"""

import json
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT_DIR / "workflow_template.json"
OUTPUT = PROJECT_DIR / "workflow.json"
REGISTRY = PROJECT_DIR / "scripts" / "n8n" / "crawlers.json"


def js_to_json_string(js_path: Path) -> str:
    content = js_path.read_text(encoding="utf-8").strip()
    content = content.replace("\\", "\\\\")
    content = content.replace('"', '\\"')
    content = content.replace("\n", "\\n")
    content = content.replace("\t", "\\t")
    content = content.replace("\r", "")
    return content


def load_selected_crawlers():
    profile = os.environ.get("JOBS_FUNNEL_PROFILE")
    if not profile:
        raise SystemExit("ERROR: JOBS_FUNNEL_PROFILE env var required")
    search_path = PROJECT_DIR / "profiles" / profile / "search.json"
    if not search_path.is_file():
        raise SystemExit(f"ERROR: {search_path} not found")
    search = json.loads(search_path.read_text(encoding="utf-8"))
    selected_ids = search.get("crawlers")
    if not selected_ids:
        raise SystemExit(f"ERROR: profiles/{profile}/search.json is missing 'crawlers' array")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in registry}
    unknown = [cid for cid in selected_ids if cid not in by_id]
    if unknown:
        raise SystemExit(
            f"ERROR: Unknown crawler ids: {unknown}. Valid: {list(by_id)}"
        )
    return [by_id[cid] for cid in selected_ids]


def emit_crawler_nodes(crawlers):
    """Return a JSON fragment: a comma-separated list of node objects (no trailing comma)."""
    nodes = []
    for c in crawlers:
        node_id = c.get("node_id") or (c["id"] + "-fetch")
        node = {
            "parameters": {"jsCode": "{{file:" + c["file"] + "}}"},
            "id": node_id,
            "name": c["name"],
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": c["position"],
        }
        nodes.append(json.dumps(node, indent=None, ensure_ascii=False))
    # Join with comma + newline to be kind to diffs
    return ",\n    ".join(nodes)


def emit_crawler_connections(crawlers):
    """Return a JSON fragment: the 'DB: Run Start' fan-out + one block per crawler -> Merge Sources.

    Emitted as object-property fragments WITHOUT enclosing braces (they live inside
    the existing connections object). The trailing comma is handled by the template.
    """
    pieces = []
    # DB: Run Start fans out to all selected crawlers at input index 0.
    fanout = {
        "main": [[{"node": c["name"], "type": "main", "index": 0} for c in crawlers]]
    }
    pieces.append(f'"DB: Run Start": {json.dumps(fanout, ensure_ascii=False)}')

    # Each crawler -> Merge Sources at a unique input index (positional in the list).
    for idx, c in enumerate(crawlers):
        conn = {
            "main": [[{"node": "Merge Sources", "type": "main", "index": idx}]]
        }
        pieces.append(f'"{c["name"]}": {json.dumps(conn, ensure_ascii=False)}')

    return ",\n    ".join(pieces)


def build():
    if not TEMPLATE.exists():
        print(f"ERROR: {TEMPLATE} not found", file=sys.stderr)
        return 1

    template_text = TEMPLATE.read_text(encoding="utf-8")

    # Phase 1: expand registry-driven placeholders BEFORE JS inlining
    # (because emit_crawler_nodes produces {{file:...}} placeholders that
    # Phase 2 will then substitute).
    crawlers = load_selected_crawlers()
    template_text = template_text.replace("{{crawler_nodes}}", emit_crawler_nodes(crawlers))
    template_text = template_text.replace("{{crawler_connections}}", emit_crawler_connections(crawlers))
    template_text = template_text.replace("{{crawler_count}}", str(len(crawlers)))

    # Phase 2: expand {{file:...}} placeholders
    pattern = re.compile(r'\{\{file:(scripts/n8n/[^}]+)\}\}')

    def replacer(match):
        rel_path = match.group(1)
        js_file = PROJECT_DIR / rel_path
        if not js_file.exists():
            print(f"WARNING: {js_file} not found, skipping", file=sys.stderr)
            return match.group(0)
        escaped = js_to_json_string(js_file)
        print(f"  Inlined {rel_path} ({len(escaped)} chars)")
        return escaped

    result = pattern.sub(replacer, template_text)

    # Validate JSON
    try:
        json.loads(result)
    except json.JSONDecodeError as e:
        print(f"ERROR: Output is not valid JSON: {e}", file=sys.stderr)
        # Write a debug copy so the user can inspect
        debug_path = PROJECT_DIR / "workflow.json.debug"
        debug_path.write_text(result, encoding="utf-8")
        print(f"Debug output at {debug_path}", file=sys.stderr)
        return 1

    OUTPUT.write_text(result, encoding="utf-8")
    print(f"\nBuilt {OUTPUT.name} successfully ({len(crawlers)} crawlers emitted)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
