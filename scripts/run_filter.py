#!/usr/bin/env python3
"""Wrapper: decode base64 job data, write temp file, run filter.py.

Usage:
    python run_filter.py <project_dir> <base64_data>

Handles Windows command-line length limits by writing data to a temp file.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: run_filter.py <project_dir> <base64_data>"}))
        sys.exit(1)

    project_dir = sys.argv[1]
    b64_data = sys.argv[2]

    # Decode base64 to JSON
    try:
        job_json = base64.b64decode(b64_data).decode("utf-8")
    except Exception as e:
        print(json.dumps({"error": f"Base64 decode failed: {e}"}))
        sys.exit(1)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    tmp.write(job_json)
    tmp.close()

    try:
        # Run filter.py with the temp file
        filter_script = os.path.join(project_dir, "scripts", "filter.py")
        env = {**os.environ, "PYTHONUTF8": "1"}
        result = subprocess.run(
            [sys.executable, filter_script, tmp.name],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        # Pass through stdout/stderr
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            sys.exit(result.returncode)
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    main()
