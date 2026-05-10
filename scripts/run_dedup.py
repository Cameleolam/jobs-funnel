#!/usr/bin/env python3
"""n8n wrapper for tiered semantic dedup."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import dedup


def _extract_ids(value) -> list[int]:
    if not isinstance(value, list):
        return []
    ids = []
    for item in value:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        try:
            ids.append(int(item["id"]))
        except (TypeError, ValueError):
            continue
    return ids


def _metrics_for(decisions):
    vector_resolved = sum(1 for d in decisions if d.decision_path in {"vector_certain", "vector_clear", "no_match"})
    claude_calls = sum(1 for d in decisions if d.decision_path.startswith("claude_"))
    return {
        "vector_resolved": vector_resolved,
        "claude_calls": claude_calls,
        "duplicates": sum(1 for d in decisions if d.existing_id is not None),
    }


def run(argv: list[str]) -> dict:
    if not argv:
        return {"pairs": [], "metrics": {"vector_resolved": 0, "claude_calls": 0, "duplicates": 0}}

    path = Path(argv[0])
    if not path.exists():
        return {"pairs": [], "metrics": {"vector_resolved": 0, "claude_calls": 0, "duplicates": 0}}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)

    job_ids = _extract_ids(payload.get("new_jobs", []))
    candidate_ids = None
    if "existing_jobs" in payload:
        candidate_ids = _extract_ids(payload.get("existing_jobs"))

    decisions = [
        dedup.find_duplicate_by_id(job_id, candidate_ids=candidate_ids)
        if candidate_ids is not None
        else dedup.find_duplicate_by_id(job_id)
        for job_id in job_ids
    ]
    pairs = [pair for pair in (d.to_pair() for d in decisions) if pair is not None]
    return {"pairs": pairs, "metrics": _metrics_for(decisions)}


def main(argv=None):
    print(json.dumps(run(sys.argv[1:] if argv is None else argv), separators=(",", ":")))


if __name__ == "__main__":
    main()
