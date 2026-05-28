"""Scoring calibration analytics service."""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from typing import Any

from ui import schema
from ui.config import TABLE
from ui.db import fetch_all


BUCKETS = (
    ("0-2", 0, 2),
    ("3-5", 3, 5),
    ("6-8", 6, 8),
    ("9-10", 9, 10),
)
APPLICATION_STATUSES = {"applied", "in_process", "offer", "rejected"}
PURSUED_STATUSES = APPLICATION_STATUSES | {"interested"}


def _score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    return score


def _status(value: Any) -> str:
    return str(value or "").strip()


def _bucket_for(score: float) -> str | None:
    for label, lower, upper in BUCKETS:
        if lower <= score <= upper:
            return label
    return None


def _rate(part: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(part / total, 4)


def _job(row: Mapping[str, Any], score: float | None = None) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "company": row.get("company") or "",
        "fit_score": score if score is not None else row.get("fit_score"),
        "decision": row.get("decision"),
        "user_status": row.get("user_status"),
    }


def _is_pending_review(row: Mapping[str, Any], has_human_review_columns: bool) -> bool:
    if row.get("decision") == "pending_review":
        return True
    return bool(has_human_review_columns and row.get("needs_human_review"))


def _is_low_confidence(row: Mapping[str, Any], has_human_review_columns: bool) -> bool:
    if not has_human_review_columns:
        return False
    raw_confidence = row.get("confidence")
    if isinstance(raw_confidence, str) and raw_confidence.strip().lower() == "low":
        return True
    confidence = _score(raw_confidence)
    return confidence is not None and confidence < 0.5


def build_scoring_summary(
    rows: list[Mapping[str, Any]],
    has_human_review_columns: bool,
) -> dict[str, Any]:
    summary = {
        "total": len(rows),
        "applied": 0,
        "dismissed": 0,
        "pending_review": 0,
        "needs_human_review": 0,
        "low_confidence": 0,
        "high_score_dismissed": 0,
        "low_score_applied": 0,
    }
    bucket_counts = {
        label: {"bucket": label, "total": 0, "applied": 0, "dismissed": 0}
        for label, _lower, _upper in BUCKETS
    }
    decisions: Counter[str] = Counter()
    user_statuses: Counter[str] = Counter()
    mismatches = {
        "high_score_dismissed": [],
        "low_score_applied": [],
        "pending_review": [],
    }

    for row in rows:
        decision = _status(row.get("decision")) or "unknown"
        user_status = _status(row.get("user_status")) or "unknown"
        score = _score(row.get("fit_score"))
        is_application = user_status in APPLICATION_STATUSES
        is_dismissed = user_status == "dismissed"
        is_pending = _is_pending_review(row, has_human_review_columns)

        decisions[decision] += 1
        user_statuses[user_status] += 1
        if is_application:
            summary["applied"] += 1
        if is_dismissed:
            summary["dismissed"] += 1
        if is_pending:
            summary["pending_review"] += 1
            mismatches["pending_review"].append(_job(row, score))
        if has_human_review_columns and row.get("needs_human_review"):
            summary["needs_human_review"] += 1
        if _is_low_confidence(row, has_human_review_columns):
            summary["low_confidence"] += 1

        if score is None:
            continue

        bucket = _bucket_for(score)
        if bucket is not None:
            bucket_counts[bucket]["total"] += 1
            if is_application:
                bucket_counts[bucket]["applied"] += 1
            if is_dismissed:
                bucket_counts[bucket]["dismissed"] += 1

        if score >= 8 and is_dismissed:
            summary["high_score_dismissed"] += 1
            mismatches["high_score_dismissed"].append(_job(row, score))
        if score <= 5 and user_status in PURSUED_STATUSES:
            summary["low_score_applied"] += 1
            mismatches["low_score_applied"].append(_job(row, score))

    buckets = []
    for label, _lower, _upper in BUCKETS:
        bucket = bucket_counts[label]
        total = bucket["total"]
        buckets.append({
            **bucket,
            "application_rate": _rate(bucket["applied"], total),
            "dismissed_rate": _rate(bucket["dismissed"], total),
        })

    return {
        "summary": summary,
        "buckets": buckets,
        "decisions": [
            {"decision": key, "count": count}
            for key, count in sorted(decisions.items(), key=lambda item: (-item[1], item[0]))
        ],
        "user_statuses": [
            {"user_status": key, "count": count}
            for key, count in sorted(user_statuses.items(), key=lambda item: (-item[1], item[0]))
        ],
        "mismatches": mismatches,
    }


def _query(has_human_review_columns: bool) -> str:
    review_columns = (
        "needs_human_review, confidence"
        if has_human_review_columns
        else "FALSE AS needs_human_review, NULL AS confidence"
    )
    return f"""
        SELECT
            id, title, company, fit_score, decision, user_status,
            {review_columns}
        FROM {TABLE}
        WHERE status = 'analyzed'
        ORDER BY analyzed_at DESC NULLS LAST, id DESC
    """


def get_scoring_summary() -> dict[str, Any]:
    has_human_review_columns = schema.HAS_HUMAN_REVIEW_COLUMNS
    rows = fetch_all(_query(has_human_review_columns))
    return build_scoring_summary(rows, has_human_review_columns)
