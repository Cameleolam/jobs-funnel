#!/usr/bin/env python3
"""NOTE: Not part of the active pipeline. Kept for future use.

Wrapper: decode base64 input, write temp file, run write_output.py.

Usage:
    python run_write_output.py <project_dir> <base64_data>
"""

import base64
import json
import os
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: run_write_output.py <project_dir> <base64_data>"}))
        sys.exit(1)

    project_dir = sys.argv[1]
    b64_data = sys.argv[2]

    try:
        input_json = base64.b64decode(b64_data).decode("utf-8")
    except Exception as e:
        print(json.dumps({"error": f"Base64 decode failed: {e}"}))
        sys.exit(1)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    tmp.write(input_json)
    tmp.close()

    try:
        script = os.path.join(project_dir, "scripts", "write_output.py")
        env = {**os.environ, "PYTHONUTF8": "1"}
        result = subprocess.run(
            [sys.executable, script, tmp.name],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            sys.exit(result.returncode)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    main()
