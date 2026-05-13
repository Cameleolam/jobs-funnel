#!/usr/bin/env python3
"""Filter job postings through the configured scoring provider.

Supports single job or batch (JSON array) input.

Usage:
    echo '{"title":"...","description":"..."}' | python filter.py
    echo '[{"title":"..."}, {"title":"..."}]' | python filter.py
    python filter.py job.json

Output: JSON assessment (object or array) with score, decision, cv_variant
"""

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from scripts.llm.types import ProviderError, ProviderTimeout
from scripts.scoring import score_input

CONFIG = json.loads((PIPELINE_DIR / "config.json").read_text(encoding="utf-8"))
PROFILE = os.environ["JOBS_FUNNEL_PROFILE"]
PROMPT_FILE = PIPELINE_DIR / "profiles" / PROFILE / "filter_prompt.md"


def _read_job_data(argv: list[str]) -> str:
    if len(argv) > 2 and argv[1] == "--base64-file":
        import base64

        return base64.b64decode("".join(argv[2:])).decode("utf-8").strip()
    if len(argv) > 2 and argv[1] == "--base64":
        import base64

        return base64.b64decode(argv[2]).decode("utf-8").strip()
    if len(argv) > 1:
        input_path = Path(argv[1])
        if not input_path.exists():
            print(json.dumps({"error": f"Input file not found: {input_path}"}))
            sys.exit(1)
        return input_path.read_text(encoding="utf-8").strip()
    return sys.stdin.read().strip()


def main():
    if not PROMPT_FILE.exists():
        print(json.dumps({"error": f"filter_prompt.md not found at {PROMPT_FILE}"}), file=sys.stderr)
        sys.exit(1)

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    job_data = _read_job_data(sys.argv)

    if not job_data:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    parsed_input = json.loads(job_data)

    try:
        assessment = score_input(
            parsed_input=parsed_input,
            system_prompt=system_prompt,
            config=CONFIG,
            root=PIPELINE_DIR,
        )
    except ProviderTimeout as exc:
        print(json.dumps({
            "error": f"{exc.provider_key} timed out after 300 seconds",
            "error_code": "TIMEOUT",
        }))
        sys.exit(1)
    except ProviderError as exc:
        print(json.dumps({
            "error": str(exc),
            "error_code": exc.error_code,
            "stderr": exc.stderr[:500] if exc.stderr else "",
            "stdout": exc.stdout[:500] if exc.stdout else "",
        }))
        sys.exit(1)

    print(json.dumps(assessment, indent=2))


if __name__ == "__main__":
    main()
