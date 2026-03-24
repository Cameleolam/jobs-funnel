#!/usr/bin/env python3
"""Generate tailored CV + cover letter using Claude Code headless mode.

Usage:
    echo '{"cv_variant":"backend","job":"...","assessment":"..."}' | python generate.py

Output: JSON with tailored_cv_html, cover_letter_text, cover_letter_html, tailoring_notes
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
PROMPT_FILE = PIPELINE_DIR / "prompts" / "generate_prompt.md"
CVS_DIR = PIPELINE_DIR / "cvs"

VARIANT_MAP = {
    "software": "software.html",
    "data": "data.html",
    "fullstack": "fullstack.html",
    "systems": "systems.html",
}


def main():
    if not PROMPT_FILE.exists():
        print(json.dumps({"error": f"generate_prompt.md not found at {PROMPT_FILE}"}), file=sys.stderr)
        sys.exit(1)

    # Read from --base64 argument, file argument, or stdin
    if len(sys.argv) > 2 and sys.argv[1] == "--base64":
        import base64
        raw_input = base64.b64decode(sys.argv[2]).decode("utf-8").strip()
    elif len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(json.dumps({"error": f"Input file not found: {input_path}"}))
            sys.exit(1)
        raw_input = input_path.read_text(encoding="utf-8").strip()
    else:
        raw_input = sys.stdin.read().strip()
    if not raw_input:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    try:
        input_data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    cv_variant = input_data.get("cv_variant", "software")
    cv_filename = VARIANT_MAP.get(cv_variant, "software.html")
    cv_file = CVS_DIR / cv_filename

    if not cv_file.exists():
        print(json.dumps({"error": f"CV file not found: {cv_file}"}))
        sys.exit(1)

    base_cv = cv_file.read_text(encoding="utf-8")
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    job_data = input_data.get("job", {})
    if isinstance(job_data, dict) and not job_data.get("description") and job_data.get("url"):
        # Fetch the job posting page to get the full description
        try:
            req = urllib.request.Request(
                job_data["url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                page_html = resp.read().decode("utf-8", errors="replace")
            # Truncate to avoid context explosion
            job_data["description"] = page_html[:8000]
        except Exception as e:
            job_data["description"] = f"(Could not fetch posting: {e})"

    assessment = input_data.get("assessment", "")

    user_prompt = (
        f"Job posting:\n\n{job_data}\n\n"
        f"Fit assessment:\n\n{assessment}\n\n"
        f"Base CV HTML (variant: {cv_variant}):\n\n{base_cv}\n\n"
        f"Generate a tailored CV and cover letter."
    )

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--model", "claude-sonnet-4-6",
                "--output-format", "json",
                "--append-system-prompt", system_prompt,
                "--max-turns", "3",
            ],
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        print(json.dumps({"error": "claude command not found"}))
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "Claude timed out after 180 seconds"}))
        sys.exit(1)

    if result.returncode != 0:
        print(json.dumps({
            "error": "claude -p returned non-zero",
            "stderr": result.stderr[:500] if result.stderr else "",
        }))
        sys.exit(1)

    raw_output = result.stdout.strip()
    result_text = raw_output

    try:
        claude_json = json.loads(raw_output)
        # Unwrap array if present (claude -p returns a list)
        if isinstance(claude_json, list) and len(claude_json) > 0:
            claude_json = claude_json[0]
        if isinstance(claude_json, dict):
            result_text = claude_json.get("result", raw_output)
    except json.JSONDecodeError:
        pass

    # Extract JSON object/array from result text, ignoring code fences and surrounding text
    clean = result_text.strip()
    json_start = -1
    for i, c in enumerate(clean):
        if c in '[{':
            json_start = i
            break
    if json_start >= 0:
        bracket = ']' if clean[json_start] == '[' else '}'
        for i in range(len(clean) - 1, json_start - 1, -1):
            if clean[i] == bracket:
                clean = clean[json_start:i + 1]
                break

    try:
        generated = json.loads(clean)
        print(json.dumps(generated, indent=2))
    except json.JSONDecodeError:
        print(json.dumps({
            "error": "Failed to parse Claude response",
            "raw": result_text[:500],
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()