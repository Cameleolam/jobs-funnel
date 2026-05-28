"""Funnel timeline analytics service."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

from ui.config import EVENTS_TABLE, TABLE
from ui.db import fetch_all


EVENT_KINDS = ("application", "contact", "interview", "task", "decision", "note")
APPLIED_STATUSES = {"applied", "in_process", "offer", "rejected"}
OPEN_STATUSES = {"interested", "applied", "in_process", "offer"}


def _clamp_weeks(value: Any) -> int:
    try:
        weeks = int(value)
    except (TypeError, ValueError):
        weeks = 12
    return max(1, min(weeks, 52))


def _status(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _days_between(start: Any, end: Any) -> float | None:
    if not start or not end:
        return None
    delta = end - start
    if hasattr(delta, "total_seconds"):
        return delta.total_seconds() / 86400
    return float(delta.days)


def _days_since(value: datetime | date, now: datetime) -> int:
    if isinstance(value, datetime):
        current = now
        if value.tzinfo is None and now.tzinfo is not None:
            current = now.replace(tzinfo=None)
        if value.tzinfo is not None and now.tzinfo is None:
            value = value.replace(tzinfo=None)
        return int((current - value).total_seconds() // 86400)
    return (now.date() - value).days


def build_funnel_timeline(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_week: dict[str, dict[str, Any]] = {}
    for row in rows:
        kind = row.get("kind")
        if kind not in EVENT_KINDS:
            continue
        week = _iso(row.get("week"))
        if not week:
            continue
        week = week[:10]
        bucket = by_week.setdefault(
            week,
            {"week": week, **{event_kind: 0 for event_kind in EVENT_KINDS}, "total": 0},
        )
        count = int(row.get("count") or 0)
        bucket[kind] += count
        bucket["total"] += count
    return [by_week[key] for key in sorted(by_week)]


def build_funnel_summary(
    rows: list[Mapping[str, Any]],
    interview_count: int,
) -> dict[str, Any]:
    close_durations = []
    summary = {
        "tracked_jobs": 0,
        "applied": 0,
        "in_process": 0,
        "rejected": 0,
        "closed": 0,
        "interviews": int(interview_count),
        "avg_days_to_close": None,
    }

    for row in rows:
        status = _status(row.get("user_status"))
        tracked_at = row.get("tracked_at")
        applied_at = row.get("applied_at")
        closed_at = row.get("closed_at")

        if tracked_at is not None:
            summary["tracked_jobs"] += 1
        if status in APPLIED_STATUSES or applied_at is not None:
            summary["applied"] += 1
        if status in OPEN_STATUSES and closed_at is None:
            summary["in_process"] += 1
        if status == "rejected":
            summary["rejected"] += 1
        if closed_at is not None:
            summary["closed"] += 1

        duration = _days_between(applied_at, closed_at)
        if duration is not None:
            close_durations.append(duration)

    if close_durations:
        summary["avg_days_to_close"] = round(sum(close_durations) / len(close_durations), 1)
    return summary


def build_stuck_jobs(
    rows: list[Mapping[str, Any]],
    now: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    stuck = []
    for row in rows:
        status = _status(row.get("user_status"))
        if row.get("tracked_at") is None or row.get("closed_at") is not None:
            continue
        if status is not None and status not in OPEN_STATUSES:
            continue

        latest = row.get("last_event_at") or row.get("tracked_at")
        if latest is None:
            continue
        days = _days_since(latest, current)
        if days <= 14:
            continue
        stuck.append((days, int(row.get("id") or 0), row, latest))

    stuck.sort(key=lambda item: (-item[0], item[1]))
    result = []
    for days, _row_id, row, _latest in stuck[:limit]:
        result.append({
            "id": row.get("id"),
            "title": row.get("title") or "",
            "company": row.get("company") or "",
            "user_status": status if (status := _status(row.get("user_status"))) else "",
            "tracked_at": _iso(row.get("tracked_at")),
            "last_event_at": _iso(row.get("last_event_at")),
            "days_since_last_event": days,
        })
    return result


def _timeline_query() -> str:
    return f"""
        SELECT date_trunc('week', occurred_at)::date AS week, kind, COUNT(*) AS count
        FROM {EVENTS_TABLE}
        WHERE kind = ANY(%s)
          AND occurred_at >= date_trunc('week', CURRENT_DATE)::timestamptz
              - ((%s - 1) * interval '1 week')
          AND occurred_at < date_trunc('week', CURRENT_DATE)::timestamptz + interval '1 week'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2 ASC
    """


def _jobs_query() -> str:
    return f"""
        SELECT id, title, company, tracked_at, applied_at, closed_at, user_status
        FROM {TABLE}
    """


def _stuck_query() -> str:
    return f"""
        SELECT
            j.id, j.title, j.company, j.tracked_at, j.closed_at, j.user_status,
            MAX(e.occurred_at) AS last_event_at
        FROM {TABLE} j
        LEFT JOIN {EVENTS_TABLE} e ON e.job_id = j.id
        WHERE j.tracked_at IS NOT NULL
        GROUP BY j.id, j.title, j.company, j.tracked_at, j.closed_at, j.user_status
    """


def get_funnel_summary(weeks: int = 12) -> dict[str, Any]:
    safe_weeks = _clamp_weeks(weeks)
    timeline_rows = fetch_all(_timeline_query(), (list(EVENT_KINDS), safe_weeks))
    weeks_payload = build_funnel_timeline(timeline_rows)
    interview_count = sum(row["interview"] for row in weeks_payload)
    job_rows = fetch_all(_jobs_query())
    stuck_rows = fetch_all(_stuck_query())
    return {
        "summary": build_funnel_summary(job_rows, interview_count),
        "weeks": weeks_payload,
        "stuck_jobs": build_stuck_jobs(stuck_rows),
    }
