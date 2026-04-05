#!/usr/bin/env python3
"""Detect semantic duplicates among job postings using Claude.

Compares newly analyzed jobs against recent existing jobs to find
postings that are likely the same position (same company, similar title)
but posted from different sources or with slight name variations.

Usage:
    python scripts/dedup_semantic.py input.json

Input JSON: { "new_jobs": [...], "existing_jobs": [...] }
Each job: { "id": int, "title": str, "company": str, "location": str }

Output JSON (stdout):
    [{"new_id": X, "existing_id": Y, "confidence": "high|medium", "reason": "..."}]
    Returns [] if no duplicates found or on any error.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

PROMPT = """\
You are a duplicate job posting detector. Compare NEW jobs against EXISTING jobs.

Identify pairs where the same position is posted by the same or very similar company,
possibly under a slightly different name, via a recruiter, or from a different source.

Rules:
- Only flag HIGH-CONFIDENCE matches where you are quite sure it's the same job.
- Same company (or parent/subsidiary) + same or very similar role title + same city = likely duplicate.
- A recruiter posting for a company counts (e.g. "Hays" posting "Python Developer at TechCo" vs "TechCo" posting "Python Developer").
- Different roles at the same company are NOT duplicates.
- Different locations for the same role are NOT duplicates.
- When in doubt, do NOT flag — false positives are worse than missed duplicates.

Return a JSON array. Each element:
{"new_id": <int>, "existing_id": <int>, "confidence": "high" or "medium", "reason": "<brief explanation>"}

Return an empty array [] if no duplicates found.

NEW JOBS:
%s

EXISTING JOBS:
%s
"""


def main():
    if len(sys.argv) < 2:
        print("[]")
        sys.exit(0)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print("[]")
        sys.exit(0)

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        input_path.unlink(missing_ok=True)
        new_jobs = data.get("new_jobs", [])
        existing_jobs = data.get("existing_jobs", [])
    except (json.JSONDecodeError, KeyError):
        print("[]")
        sys.exit(0)

    if not new_jobs or not existing_jobs:
        print("[]")
        sys.exit(0)

    # Format jobs for the prompt (compact, just what Claude needs)
    def fmt(jobs):
        return json.dumps(
            [{"id": j["id"], "title": j["title"], "company": j["company"], "location": j["location"]} for j in jobs],
            indent=2,
        )

    prompt = PROMPT % (fmt(new_jobs), fmt(existing_jobs))

    # Call Claude
    try:
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--max-turns", "1",
        ]
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("[]")
        sys.exit(0)
    except subprocess.TimeoutExpired:
        print("[]")
        sys.exit(0)

    if result.returncode != 0:
        print("[]")
        sys.exit(0)

    # Parse Claude's response
    try:
        response = json.loads(result.stdout)
        # claude -p wraps in {"result": "..."} format
        if isinstance(response, dict) and "result" in response:
            inner = response["result"]
            if isinstance(inner, str):
                inner = json.loads(inner)
            response = inner
        if not isinstance(response, list):
            response = []
    except (json.JSONDecodeError, TypeError):
        print("[]")
        sys.exit(0)

    # Validate each result
    valid_ids_new = {j["id"] for j in new_jobs}
    valid_ids_existing = {j["id"] for j in existing_jobs}
    validated = []
    for item in response:
        if not isinstance(item, dict):
            continue
        new_id = item.get("new_id")
        existing_id = item.get("existing_id")
        confidence = item.get("confidence", "medium")
        reason = item.get("reason", "")
        if new_id in valid_ids_new and existing_id in valid_ids_existing and confidence in ("high", "medium"):
            validated.append({
                "new_id": new_id,
                "existing_id": existing_id,
                "confidence": confidence,
                "reason": str(reason)[:200],
            })

    print(json.dumps(validated))


if __name__ == "__main__":
    main()
