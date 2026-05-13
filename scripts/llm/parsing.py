from __future__ import annotations

import json
import re
from typing import Any


def extract_result_text(stdout: str) -> str:
    text = (stdout or "").strip()
    try:
        wrapped = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(wrapped, list) and wrapped:
        wrapped = wrapped[0]
    if isinstance(wrapped, dict) and isinstance(wrapped.get("result"), str):
        return wrapped["result"].strip()
    return text


def _strip_code_fence(text: str) -> str:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean)
    return clean.strip()


def _slice_json_region(text: str) -> str:
    clean = _strip_code_fence(text)
    decoder = json.JSONDecoder()
    for start, char in enumerate(clean):
        if char not in "[{":
            continue
        try:
            _, end = decoder.raw_decode(clean, start)
        except json.JSONDecodeError:
            continue
        return clean[start:end]
    return clean


def loads_jsonish(text: str) -> Any:
    candidate = _slice_json_region(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(
            r"([{\[,]\s*)'([A-Za-z_][A-Za-z0-9_]*)'\s*:",
            r'\1"\2":',
            candidate,
        )
        candidate = _slice_json_region(repaired)
        return json.loads(candidate)


def fallback_assessment(blocker: str, reasoning: str, error_code: str) -> dict[str, Any]:
    return {
        "fit_score": 0,
        "decision": "SKIP",
        "cv_variant": "default",
        "hard_blockers": [blocker],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": reasoning,
        "priority_notes": None,
        "error_code": error_code,
    }


def batch_padding_assessment(index: int, expected_count: int) -> dict[str, Any]:
    return {
        "fit_score": 0,
        "decision": "SKIP",
        "cv_variant": "default",
        "hard_blockers": ["Batch evaluation incomplete"],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": f"Missing from batch response (job {index} of {expected_count})",
        "priority_notes": "BATCH_PADDING",
        "error_code": "BATCH_PADDING",
    }


def coerce_assessment_list(assessment: Any, expected_count: int) -> list[dict[str, Any]]:
    if isinstance(assessment, list):
        result = [
            item
            if isinstance(item, dict)
            else fallback_assessment(
                blocker="Scoring provider returned a non-object batch item",
                reasoning=f"Invalid batch item: {repr(item)[:200]}",
                error_code="PARSE_FAIL",
            )
            for item in assessment
        ]
    elif isinstance(assessment, dict):
        result = [assessment]
    else:
        result = [
            fallback_assessment(
                blocker="Scoring provider returned non-JSON assessment shape",
                reasoning=f"Invalid assessment shape: {type(assessment).__name__}",
                error_code="PARSE_FAIL",
            )
        ]

    while len(result) < expected_count:
        result.append(batch_padding_assessment(len(result) + 1, expected_count))
    return result[:expected_count]
