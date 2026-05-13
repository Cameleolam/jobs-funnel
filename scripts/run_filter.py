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

DEFAULT_WRAPPER_TIMEOUT_SECONDS = 3600


def _wrapper_timeout_seconds():
    try:
        value = int(os.environ.get("SCORING_WRAPPER_TIMEOUT_SECONDS", str(DEFAULT_WRAPPER_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_WRAPPER_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_WRAPPER_TIMEOUT_SECONDS


def _input_count(job_json):
    try:
        payload = json.loads(job_json)
    except Exception:
        return 1, False
    if isinstance(payload, list):
        return len(payload), True
    return 1, False


def _fallback_assessment(blocker, reasoning, error_code):
    return {
        "fit_score": 0,
        "decision": "SKIP",
        "cv_variant": "software",
        "hard_blockers": [blocker],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": reasoning,
        "priority_notes": None,
        "error_code": error_code,
    }


def _fallback_payload(job_json, blocker, reasoning, error_code):
    count, is_batch = _input_count(job_json)
    if is_batch:
        return [
            _fallback_assessment(blocker, reasoning, error_code)
            for _ in range(count)
        ]
    return _fallback_assessment(blocker, reasoning, error_code)


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
            job_json = open(file_path, encoding="utf-8").read()
        except OSError:
            job_json = "{}"
        try:
            result = subprocess.run(
                [sys.executable, filter_script, file_path],
                capture_output=True,
                text=True,
                timeout=_wrapper_timeout_seconds(),
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            if result.stdout:
                print(result.stdout, end="")
            elif result.returncode != 0:
                # filter.py failed without output - emit fallback SKIP
                err_msg = (result.stderr or "Unknown error")[:200]
                print(json.dumps(_fallback_payload(
                    job_json,
                    f"Filter error: {err_msg}",
                    f"filter.py failed: {err_msg}",
                    "API_ERROR",
                )))
        except subprocess.TimeoutExpired:
            timeout = _wrapper_timeout_seconds()
            print(json.dumps(_fallback_payload(
                job_json,
                "Filter timed out",
                f"filter.py timed out after {timeout} seconds",
                "TIMEOUT",
            )))
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
            timeout=_wrapper_timeout_seconds(),
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(result.stdout, end="")
        elif result.returncode != 0:
            err_msg = (result.stderr or "Unknown error")[:200]
            print(json.dumps(_fallback_payload(
                job_json,
                f"Filter error: {err_msg}",
                f"filter.py failed: {err_msg}",
                "API_ERROR",
            )))
    except subprocess.TimeoutExpired:
        timeout = _wrapper_timeout_seconds()
        print(json.dumps(_fallback_payload(
            job_json,
            "Filter timed out",
            f"filter.py timed out after {timeout} seconds",
            "TIMEOUT",
        )))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    main()
