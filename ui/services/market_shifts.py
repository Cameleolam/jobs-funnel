"""Weekly market topic analytics service."""
from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from ui.config import TABLE
from ui.db import fetch_all


GENERIC_TAGS = {
    "ats",
    "remote",
    "full-time",
    "full time",
    "part-time",
    "part time",
    "contract",
    "freelance",
    "internship",
    "permanent",
}
TITLE_STOPWORDS = GENERIC_TAGS | {
    "a",
    "an",
    "and",
    "d",
    "developer",
    "engineer",
    "f",
    "fullstack",
    "full-stack",
    "lead",
    "m",
    "manager",
    "of",
    "senior",
    "software",
    "the",
    "to",
    "w",
}
SIGNAL_DECISIONS = {"pass", "maybe"}
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")


def _clamp_int(value: Any, default: int, lower: int, upper: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(lower, min(number, upper))


def _normalize_topic(value: Any) -> str | None:
    if not isinstance(value, (str, int, float, bool)):
        return None
    topic = str(value or "").strip().lower()
    if not topic or topic in GENERIC_TAGS:
        return None
    return topic


def _tag_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped.split(",")
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]
    return []


def _unique_limited(values: list[str], limit: int = 3) -> list[str]:
    topics = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        topics.append(value)
        if len(topics) == limit:
            break
    return topics


def extract_topics(row: Mapping[str, Any]) -> list[str]:
    tag_topics = []
    for value in _tag_values(row.get("tags")):
        topic = _normalize_topic(value)
        if topic:
            tag_topics.append(topic)
    if tag_topics:
        return _unique_limited(tag_topics)

    title_topics = []
    for match in TOKEN_RE.findall(str(row.get("title") or "").lower()):
        if match in TITLE_STOPWORDS:
            continue
        title_topics.append(match)
    return _unique_limited(title_topics)


def _iso_week(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        current = value.date()
    elif isinstance(value, date):
        current = value
    else:
        try:
            current = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None
    week = current.fromordinal(current.toordinal() - current.weekday())
    return week.isoformat()


def _is_signal(row: Mapping[str, Any]) -> bool:
    return str(row.get("decision") or "").strip().lower() in SIGNAL_DECISIONS


def _market_date(row: Mapping[str, Any]) -> Any:
    for key in ("posted_at", "crawled_at", "market_date", "analyzed_at"):
        value = row.get(key)
        if value is not None:
            return value
    return None


def _date_basis(row: Mapping[str, Any]) -> str:
    for key in ("posted_at", "crawled_at", "analyzed_at"):
        if row.get(key) is not None:
            return key
    return "unknown"


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def _normalize_date_mode(value: Any) -> str:
    return "fallback" if value == "fallback" else "posted"


def _topic_summary(topic: str, total: int, signal_total: int) -> dict[str, Any]:
    return {
        "topic": topic,
        "total": total,
        "signal_total": signal_total,
        "signal_rate": _rate(signal_total, total),
    }


def _build_insights(
    topics: list[dict[str, Any]],
    weeks: list[str],
) -> dict[str, list[dict[str, Any]]]:
    previous_week = weeks[-2] if len(weeks) >= 2 else None
    current_week = weeks[-1] if weeks else None
    movement = []
    for topic in topics:
        by_week = {item["week"]: item for item in topic["weeks"]}
        previous = by_week.get(previous_week, {}).get("count", 0) if previous_week else 0
        current = by_week.get(current_week, {}).get("count", 0) if current_week else 0
        movement.append({
            **_topic_summary(topic["topic"], topic["total"], topic["signal_total"]),
            "previous": previous,
            "current": current,
            "delta": current - previous,
        })

    rising = sorted(
        [item for item in movement if item["delta"] > 0],
        key=lambda item: (-item["delta"], -item["current"], item["topic"]),
    )
    fading = sorted(
        [item for item in movement if item["delta"] < 0],
        key=lambda item: (item["delta"], -item["previous"], item["topic"]),
    )
    high_signal = sorted(
        [item for item in movement if item["signal_total"] > 0],
        key=lambda item: (-item["signal_rate"], -item["signal_total"], -item["total"], item["topic"]),
    )
    noisy = sorted(
        [item for item in movement if item["total"] >= 2 and item["signal_rate"] < 0.5],
        key=lambda item: (-item["total"], item["signal_rate"], item["topic"]),
    )
    return {
        "rising_topics": rising[:5],
        "fading_topics": fading[:5],
        "high_signal_topics": high_signal[:5],
        "noisy_topics": noisy[:5],
    }


def build_market_shift_series(
    rows: list[Mapping[str, Any]],
    limit: int = 20,
    date_mode: str = "posted",
) -> dict[str, Any]:
    safe_limit = _clamp_int(limit, 20, 1, 50)
    safe_date_mode = _normalize_date_mode(date_mode)
    weeks = sorted({
        week
        for row in rows
        if (week := _iso_week(_market_date(row))) is not None
    })
    counts: dict[str, Counter[str]] = {}
    signal_counts: dict[str, Counter[str]] = {}
    topic_totals: Counter[str] = Counter()
    topic_signal_totals: Counter[str] = Counter()
    date_basis: Counter[str] = Counter()
    signal_jobs = 0

    for row in rows:
        date_basis[_date_basis(row)] += 1
        week = _iso_week(_market_date(row))
        if week is None:
            continue
        is_signal = _is_signal(row)
        if is_signal:
            signal_jobs += 1
        for topic in extract_topics(row):
            counts.setdefault(topic, Counter())[week] += 1
            topic_totals[topic] += 1
            if is_signal:
                signal_counts.setdefault(topic, Counter())[week] += 1
                topic_signal_totals[topic] += 1

    ordered_topics = sorted(
        topic_totals,
        key=lambda topic: (-topic_totals[topic], -topic_signal_totals[topic], topic),
    )
    topics = []
    for topic in ordered_topics[:safe_limit]:
        topics.append({
            "topic": topic,
            "total": topic_totals[topic],
            "signal_total": topic_signal_totals[topic],
            "weeks": [
                {
                    "week": week,
                    "count": counts.get(topic, Counter())[week],
                    "signal_count": signal_counts.get(topic, Counter())[week],
                }
                for week in weeks
            ],
        })

    return {
        "weeks": weeks,
        "topics": topics,
        "summary": {
            "total_jobs": len(rows),
            "topic_count": len(topic_totals),
            "signal_jobs": signal_jobs,
            "date_mode": safe_date_mode,
            "date_basis": {
                "posted_at": date_basis["posted_at"],
                "crawled_at": date_basis["crawled_at"],
                "analyzed_at": date_basis["analyzed_at"],
                "unknown": date_basis["unknown"],
            },
        },
        "insights": _build_insights(topics, weeks),
    }


def _query(date_mode: str = "posted") -> str:
    if _normalize_date_mode(date_mode) == "fallback":
        market_date = "COALESCE(posted_at, crawled_at, analyzed_at) AS market_date"
        required_date_filter = ""
    else:
        market_date = "posted_at AS market_date"
        required_date_filter = "AND posted_at IS NOT NULL"

    return f"""
        WITH analyzed_jobs AS (
            SELECT
                id, title, tags, decision, posted_at, crawled_at, analyzed_at,
                {market_date}
            FROM {TABLE}
            WHERE status = 'analyzed'
              {required_date_filter}
        )
        SELECT id, title, tags, decision, posted_at, crawled_at, analyzed_at, market_date
        FROM analyzed_jobs
        WHERE market_date >= date_trunc('week', CURRENT_DATE)::timestamptz
              - ((%s - 1) * interval '1 week')
          AND market_date < date_trunc('week', CURRENT_DATE)::timestamptz + interval '1 week'
        ORDER BY market_date DESC
    """


def get_market_shifts(
    weeks: int = 12,
    limit: int = 20,
    date_mode: str = "posted",
) -> dict[str, Any]:
    safe_weeks = _clamp_int(weeks, 12, 1, 52)
    safe_limit = _clamp_int(limit, 20, 1, 50)
    safe_date_mode = _normalize_date_mode(date_mode)
    rows = fetch_all(_query(safe_date_mode), (safe_weeks,))
    return build_market_shift_series(rows, limit=safe_limit, date_mode=safe_date_mode)
