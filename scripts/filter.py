#!/usr/bin/env python3
"""Filter job postings using Claude Code headless mode.

Supports single job or batch (JSON array) input.

Usage:
    echo '{"title":"...","description":"..."}' | python filter.py
    echo '[{"title":"..."}, {"title":"..."}]' | python filter.py
    python filter.py job.json

Output: JSON assessment (object or array) with score, decision, cv_variant
"""

import json
import re
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

    # Read from --base64-file (writes temp file from b64 chunks), --base64, file, or stdin
    if len(sys.argv) > 2 and sys.argv[1] == "--base64-file":
        import base64
        b64_str = "".join(sys.argv[2:])
        job_data = base64.b64decode(b64_str).decode("utf-8").strip()
    elif len(sys.argv) > 2 and sys.argv[1] == "--base64":
        import base64
        job_data = base64.b64decode(sys.argv[2]).decode("utf-8").strip()
    elif len(sys.argv) > 1:
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

    # Detect batch (array) vs single (object) input
    parsed_input = json.loads(job_data)
    is_batch = isinstance(parsed_input, list)

    if is_batch:
        user_prompt = f"Evaluate these {len(parsed_input)} job postings:\n\n"
        for i, job in enumerate(parsed_input):
            user_prompt += f"--- JOB {i + 1} ---\n{json.dumps(job)}\n\n"
    else:
        user_prompt = f"Evaluate this job posting:\n\n{job_data}"

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
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print(json.dumps({"error": "claude command not found. Is Claude Code installed?"}))
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "Claude timed out after 300 seconds"}))
        sys.exit(1)

    if result.returncode != 0:
        print(json.dumps({
            "error": "claude -p returned non-zero",
            "stderr": result.stderr[:500] if result.stderr else "",
        }))
        sys.exit(1)

    # Parse Claude's JSON wrapper to extract the result text
    # claude -p --output-format json returns either {"result":...} or [{"result":...}]
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
        pass  # Not wrapped in Claude's JSON format, use raw

    # Clean markdown code fences (robust — handles whitespace variations)
    clean = result_text.strip()
    # Try to find JSON array or object directly, ignoring any surrounding text/fences
    # This handles cases where result_text has code fences, extra whitespace, etc.
    json_start = -1
    json_end = -1
    for i, c in enumerate(clean):
        if c in '[{':
            json_start = i
            break
    if json_start >= 0:
        # Find matching closing bracket
        bracket = ']' if clean[json_start] == '[' else '}'
        depth = 0
        for i in range(len(clean) - 1, json_start - 1, -1):
            if clean[i] == bracket:
                json_end = i + 1
                break
        if json_end > json_start:
            clean = clean[json_start:json_end]

    # Validate and output
    try:
        assessment = json.loads(clean)
    except json.JSONDecodeError:
        # Output SKIP fallback instead of failing — let downstream nodes handle it
        fallback = {
            "fit_score": 0,
            "decision": "SKIP",
            "cv_variant": "software",
            "hard_blockers": ["Claude response parse error"],
            "soft_gaps": [],
            "strong_matches": [],
            "reasoning": f"Parse error: {result_text[:200]}",
            "priority_notes": None,
        }
        if is_batch:
            print(json.dumps([fallback] * len(parsed_input), indent=2))
        else:
            print(json.dumps(fallback, indent=2))
        sys.exit(0)

    # For batch input, ensure we got an array with the right count
    if is_batch:
        if not isinstance(assessment, list):
            assessment = [assessment]
        # Pad with SKIP entries if Claude returned fewer results
        while len(assessment) < len(parsed_input):
            assessment.append({
                "fit_score": 0,
                "decision": "SKIP",
                "cv_variant": "software",
                "hard_blockers": ["Batch evaluation incomplete"],
                "soft_gaps": [],
                "strong_matches": [],
                "reasoning": f"Missing from batch response (job {len(assessment)+1} of {len(parsed_input)})",
                "priority_notes": "BATCH_PADDING",
            })

    print(json.dumps(assessment, indent=2))


if __name__ == "__main__":
    main()
