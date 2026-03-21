#!/usr/bin/env python3
"""Filter a job posting using Claude Code headless mode.

Usage:
    echo '{"title":"...","description":"..."}' | python filter.py
    python filter.py < job.json

Output: JSON assessment with score, decision, cv_variant
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
PROMPT_FILE = PIPELINE_DIR / "prompts" / "filter_prompt.md"


def main():
    if not PROMPT_FILE.exists():
        print(json.dumps({"error": f"filter_prompt.md not found at {PROMPT_FILE}"}), file=sys.stderr)
        sys.exit(1)

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    # Read from file argument or stdin
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(json.dumps({"error": f"Input file not found: {input_path}"}))
            sys.exit(1)
        job_data = input_path.read_text(encoding="utf-8").strip()
    else:
        job_data = sys.stdin.read().strip()

    if not job_data:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    user_prompt = f"Evaluate this job posting:\n\n{job_data}"

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--output-format", "json",
                "--append-system-prompt", system_prompt,
                "--max-turns", "1",
            ],
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print(json.dumps({"error": "claude command not found. Is Claude Code installed?"}))
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

    # Parse Claude's JSON wrapper to extract the result text
    raw_output = result.stdout.strip()
    result_text = raw_output

    try:
        claude_json = json.loads(raw_output)
        result_text = claude_json.get("result", raw_output)
    except json.JSONDecodeError:
        pass  # Not wrapped in Claude's JSON format, use raw

    # Clean markdown code fences
    clean = result_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    # Validate and output
    try:
        assessment = json.loads(clean)
        print(json.dumps(assessment, indent=2))
    except json.JSONDecodeError:
        print(json.dumps({
            "error": "Failed to parse Claude response as JSON",
            "raw": result_text[:500],
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()