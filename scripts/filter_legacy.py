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

from scripts.llm.parsing import fallback_assessment
from scripts.llm.types import ProviderError, ProviderTimeout
from scripts.scoring import score_input

CONFIG = json.loads((PIPELINE_DIR / "config.json").read_text(encoding="utf-8"))
PROFILE = os.environ["JOBS_FUNNEL_PROFILE"]
PROMPT_FILE = PIPELINE_DIR / "profiles" / PROFILE / "filter_prompt.md"


class FilterInputError(Exception):
    pass


def _fallback_for_input(parsed_input, blocker: str, reasoning: str, error_code: str, **extra):
    fallback = fallback_assessment(blocker=blocker, reasoning=reasoning, error_code=error_code)
    fallback.update(extra)
    if isinstance(parsed_input, list):
        return [dict(fallback) for _ in parsed_input]
    return fallback


def _print_fallback(parsed_input, blocker: str, reasoning: str, error_code: str, **extra) -> None:
    print(json.dumps(_fallback_for_input(parsed_input, blocker, reasoning, error_code, **extra), indent=2))


def _decode_base64(value: str) -> str:
    import base64

    try:
        return base64.b64decode(value, validate=True).decode("utf-8").strip()
    except Exception as exc:
        raise FilterInputError(f"Filter error: invalid base64 input: {exc}") from exc


def _read_job_data(argv: list[str]) -> str:
    if len(argv) > 2 and argv[1] == "--base64-file":
        b64_source = Path(argv[2])
        if b64_source.exists():
            b64_str = b64_source.read_text(encoding="utf-8").strip()
        else:
            b64_str = "".join(argv[2:])
        return _decode_base64(b64_str)
    if len(argv) > 2 and argv[1] == "--base64":
        return _decode_base64(argv[2])
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
    try:
        job_data = _read_job_data(sys.argv)
    except FilterInputError as exc:
        _print_fallback(None, "Filter error: invalid input", str(exc), "API_ERROR")
        sys.exit(1)

    if not job_data:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    try:
        parsed_input = json.loads(job_data)
    except json.JSONDecodeError as exc:
        _print_fallback(None, "Parse error: invalid JSON input", f"Parse error: {exc}", "PARSE_FAIL")
        sys.exit(1)

    try:
        assessment = score_input(
            parsed_input=parsed_input,
            system_prompt=system_prompt,
            config=CONFIG,
            root=PIPELINE_DIR,
        )
    except ProviderTimeout as exc:
        reasoning = f"{exc.provider_key} timed out after 300 seconds"
        _print_fallback(parsed_input, "Scoring provider timed out", reasoning, "TIMEOUT")
        sys.exit(1)
    except ProviderError as exc:
        _print_fallback(
            parsed_input,
            "Filter error: scoring provider failed",
            str(exc),
            exc.error_code,
            stderr=exc.stderr[:500] if exc.stderr else "",
            stdout=exc.stdout[:500] if exc.stdout else "",
        )
        sys.exit(1)

    print(json.dumps(assessment, indent=2))


if __name__ == "__main__":
    main()
