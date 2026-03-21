#!/usr/bin/env python3
"""Parse a job posting HTML page using Claude Code headless mode.

Usage:
    cat page.html | python parse.py
    python parse.py < page.html

Output: JSON with title, company, location, description, etc.
"""

import json
import subprocess
import sys
from pathlib import Path

SYSTEM_PROMPT = """You are a job posting parser. Extract structured data from this HTML.
Return ONLY a valid JSON object with these fields:
- title (string)
- company (string)
- location (string)
- employment_type (string or null)
- experience_required (string or null)
- tech_stack (array of strings)
- language_requirements (string or null)
- salary_range (string or null)
- description (string: the full job description as clean plain text, max 3000 chars)

If a field is not found, set it to null. Return ONLY JSON, no explanation."""


def main():
    # Read from file argument or stdin
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(json.dumps({"error": f"Input file not found: {input_path}"}))
            sys.exit(1)
        html = input_path.read_text(encoding="utf-8").strip()
    else:
        html = sys.stdin.read().strip()
    if not html:
        print(json.dumps({"error": "No HTML provided on stdin"}))
        sys.exit(1)

    # Truncate to avoid blowing context
    html = html[:15000]

    user_prompt = f"Parse this job posting HTML and extract structured data as JSON:\n\n{html}"

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--output-format", "json",
                "--append-system-prompt", SYSTEM_PROMPT,
                "--max-turns", "1",
            ],
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print(json.dumps({"error": "claude command not found"}))
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "Claude timed out after 120 seconds"}))
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
        result_text = claude_json.get("result", raw_output)
    except json.JSONDecodeError:
        pass

    clean = result_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    try:
        parsed = json.loads(clean)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print(json.dumps({
            "error": "Failed to parse Claude response",
            "raw": result_text[:500],
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()