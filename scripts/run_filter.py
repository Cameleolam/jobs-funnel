#!/usr/bin/env python3
"""Wrapper: decode base64 job data or read from file, run filter.py.

Usage:
    python run_filter.py <project_dir> <base64_data>
    python run_filter.py <project_dir> --file <json_file_path>

Handles Windows command-line length limits by supporting file-based input.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: run_filter.py <project_dir> <base64_data> | --file <path>"}))
        sys.exit(1)

    project_dir = sys.argv[1]
    filter_script = os.path.join(project_dir, "scripts", "filter.py")
    env = {**os.environ, "PYTHONUTF8": "1"}

    # Delay between sequential calls to avoid rate limits
    time.sleep(1)

    # --file mode: JSON file already on disk, pass directly to filter.py
    if sys.argv[2] == "--file":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "--file requires a file path argument"}))
            sys.exit(1)
        file_path = sys.argv[3]
        if not os.path.exists(file_path):
            print(json.dumps({"error": f"File not found: {file_path}"}))
            sys.exit(1)
        try:
            result = subprocess.run(
                [sys.executable, filter_script, file_path],
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            if result.stdout:
                print(result.stdout, end="")
            elif result.returncode != 0:
                # filter.py failed without output - emit fallback SKIP
                err_msg = (result.stderr or "Unknown error")[:200]
                print(json.dumps([{
                    "fit_score": 0, "decision": "SKIP", "cv_variant": "software",
                    "hard_blockers": [f"Filter error: {err_msg}"],
                    "soft_gaps": [], "strong_matches": [],
                    "reasoning": f"filter.py failed: {err_msg}",
                    "priority_notes": None,
                }]))
        except subprocess.TimeoutExpired:
            print(json.dumps([{
                "fit_score": 0, "decision": "SKIP", "cv_variant": "software",
                "hard_blockers": ["Claude timed out"],
                "soft_gaps": [], "strong_matches": [],
                "reasoning": "filter.py timed out after 300 seconds",
                "priority_notes": None,
            }]))
        finally:
            # Clean up the batch temp file
            try:
                os.unlink(file_path)
            except OSError:
                pass
        return

    # Legacy mode: base64 data as CLI argument
    b64_data = sys.argv[2]

    try:
        job_json = base64.b64decode(b64_data).decode("utf-8")
    except Exception as e:
        print(json.dumps({"error": f"Base64 decode failed: {e}"}))
        sys.exit(1)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    tmp.write(job_json)
    tmp.close()

    try:
        result = subprocess.run(
            [sys.executable, filter_script, tmp.name],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(result.stdout, end="")
        elif result.returncode != 0:
            err_msg = (result.stderr or "Unknown error")[:200]
            print(json.dumps({
                "fit_score": 0, "decision": "SKIP", "cv_variant": "software",
                "hard_blockers": [f"Filter error: {err_msg}"],
                "soft_gaps": [], "strong_matches": [],
                "reasoning": f"filter.py failed: {err_msg}",
                "priority_notes": None,
            }))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    main()
