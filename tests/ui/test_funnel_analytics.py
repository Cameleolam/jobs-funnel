from datetime import date, datetime, timezone

from ui.services import funnel_analytics


def test_build_funnel_timeline_counts_events_by_week_and_fills_missing_kinds():
    rows = [
        {"week": date(2026, 5, 4), "kind": "application", "count": 2},
        {"week": date(2026, 5, 4), "kind": "interview", "count": 1},
        {"week": date(2026, 5, 11), "kind": "note", "count": 3},
        {"week": date(2026, 5, 11), "kind": "unknown", "count": 9},
    ]

    assert funnel_analytics.build_funnel_timeline(rows) == [
        {
            "week": "2026-05-04",
            "application": 2,
            "contact": 0,
            "interview": 1,
            "task": 0,
            "decision": 0,
            "note": 0,
            "total": 3,
        },
        {
            "week": "2026-05-11",
            "application": 0,
            "contact": 0,
            "interview": 0,
            "task": 0,
            "decision": 0,
            "note": 3,
            "total": 3,
        },
    ]


def test_build_summary_counts_jobs_and_interviews():
    rows = [
        {
            "tracked_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "applied_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 4, 12, tzinfo=timezone.utc),
            "user_status": "rejected",
        },
        {
            "tracked_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
            "applied_at": None,
            "closed_at": None,
            "user_status": "interested",
        },
        {
            "tracked_at": datetime(2026, 4, 4, tzinfo=timezone.utc),
            "applied_at": datetime(2026, 4, 5, tzinfo=timezone.utc),
            "closed_at": None,
            "user_status": None,
        },
        {
            "tracked_at": None,
            "applied_at": None,
            "closed_at": None,
            "user_status": "applied",
        },
    ]

    summary = funnel_analytics.build_funnel_summary(rows, interview_count=4)

    assert summary == {
        "tracked_jobs": 3,
        "applied": 3,
        "in_process": 2,
        "rejected": 1,
        "closed": 1,
        "interviews": 4,
        "avg_days_to_close": 10.0,
    }


def test_build_stuck_jobs_uses_latest_event_or_tracked_at_and_limits_results():
    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    rows = [
        {
            "id": 1,
            "title": "Oldest",
            "company": "Acme",
            "user_status": "applied",
            "tracked_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "last_event_at": datetime(2026, 4, 15, tzinfo=timezone.utc),
            "closed_at": None,
        },
        {
            "id": 2,
            "title": "Fresh",
            "company": "Beta",
            "user_status": "in_process",
            "tracked_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
            "last_event_at": None,
            "closed_at": None,
        },
        {
            "id": 3,
            "title": "Closed",
            "company": "Gamma",
            "user_status": "offer",
            "tracked_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "last_event_at": None,
            "closed_at": datetime(2026, 4, 20, tzinfo=timezone.utc),
        },
        {
            "id": 4,
            "title": "Unspecified",
            "company": "Delta",
            "user_status": None,
            "tracked_at": datetime(2026, 4, 10, tzinfo=timezone.utc),
            "last_event_at": None,
            "closed_at": None,
        },
    ]

    stuck = funnel_analytics.build_stuck_jobs(rows, now=now, limit=2)

    assert stuck == [
        {
            "id": 4,
            "title": "Unspecified",
            "company": "Delta",
            "user_status": "",
            "tracked_at": "2026-04-10T00:00:00+00:00",
            "last_event_at": None,
            "days_since_last_event": 48,
        },
        {
            "id": 1,
            "title": "Oldest",
            "company": "Acme",
            "user_status": "applied",
            "tracked_at": "2026-04-01T00:00:00+00:00",
            "last_event_at": "2026-04-15T00:00:00+00:00",
            "days_since_last_event": 43,
        }
    ]


def test_get_funnel_summary_normalizes_and_clamps_weeks(monkeypatch):
    seen_weeks = []

    def fake_fetch_all(query, params=()):
        if params:
            seen_weeks.append(params[1])
            return []
        return []

    monkeypatch.setattr(funnel_analytics, "fetch_all", fake_fetch_all)

    funnel_analytics.get_funnel_summary(weeks="abc")
    funnel_analytics.get_funnel_summary(weeks="12.5")
    funnel_analytics.get_funnel_summary(weeks=999)
    funnel_analytics.get_funnel_summary(weeks=-3)

    assert seen_weeks == [12, 12, 52, 1]


def test_get_funnel_summary_counts_all_time_interviews_independent_from_timeline(monkeypatch):
    calls = []

    def fake_fetch_all(query, params=()):
        calls.append((query, params))
        if params:
            return [
                {"week": date(2026, 5, 4), "kind": "application", "count": 1},
            ]
        if "COUNT(*) AS count" in query:
            return [{"count": 3}]
        return []

    monkeypatch.setattr(funnel_analytics, "fetch_all", fake_fetch_all)

    payload = funnel_analytics.get_funnel_summary(weeks=1)

    assert payload["weeks"] == [
        {
            "week": "2026-05-04",
            "application": 1,
            "contact": 0,
            "interview": 0,
            "task": 0,
            "decision": 0,
            "note": 0,
            "total": 1,
        }
    ]
    assert payload["summary"]["interviews"] == 3
    assert len(calls) == 4
