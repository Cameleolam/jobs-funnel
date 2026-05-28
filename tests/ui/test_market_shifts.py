from datetime import date, datetime, timezone

from ui.services import market_shifts


def test_build_market_shift_series_groups_topics_by_week_and_fills_topic_weeks():
    rows = [
        {
            "title": "Backend Engineer",
            "tags": ["backend", "python"],
            "decision": "PASS",
            "analyzed_at": datetime(2026, 5, 5, tzinfo=timezone.utc),
        },
        {
            "title": "Frontend Developer",
            "tags": ["frontend", "backend"],
            "decision": "MAYBE",
            "analyzed_at": datetime(2026, 5, 12, tzinfo=timezone.utc),
        },
        {
            "title": "Data Engineer",
            "tags": ["data"],
            "decision": "NO",
            "analyzed_at": datetime(2026, 5, 12, tzinfo=timezone.utc),
        },
    ]

    payload = market_shifts.build_market_shift_series(rows, limit=2)

    assert payload["weeks"] == ["2026-05-04", "2026-05-11"]
    assert payload["topics"] == [
        {
            "topic": "backend",
            "total": 2,
            "signal_total": 2,
            "weeks": [
                {"week": "2026-05-04", "count": 1, "signal_count": 1},
                {"week": "2026-05-11", "count": 1, "signal_count": 1},
            ],
        },
        {
            "topic": "frontend",
            "total": 1,
            "signal_total": 1,
            "weeks": [
                {"week": "2026-05-04", "count": 0, "signal_count": 0},
                {"week": "2026-05-11", "count": 1, "signal_count": 1},
            ],
        },
    ]
    assert payload["summary"] == {
        "total_jobs": 3,
        "topic_count": 4,
        "signal_jobs": 2,
        "date_mode": "posted",
        "date_basis": {
            "posted_at": 0,
            "crawled_at": 0,
            "analyzed_at": 3,
            "unknown": 0,
        },
    }
    assert payload["insights"]["high_signal_topics"][0]["topic"] == "backend"


def test_build_market_shift_series_uses_posted_date_with_crawl_and_analysis_fallbacks():
    rows = [
        {
            "title": "Backend Engineer",
            "tags": ["backend"],
            "decision": "PASS",
            "posted_at": datetime(2026, 5, 12, tzinfo=timezone.utc),
            "crawled_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
            "analyzed_at": datetime(2026, 5, 25, tzinfo=timezone.utc),
        },
        {
            "title": "Platform Engineer",
            "tags": ["platform"],
            "decision": "SKIP",
            "posted_at": None,
            "crawled_at": datetime(2026, 5, 19, tzinfo=timezone.utc),
            "analyzed_at": datetime(2026, 5, 25, tzinfo=timezone.utc),
        },
        {
            "title": "Data Engineer",
            "tags": ["data"],
            "decision": "MAYBE",
            "posted_at": None,
            "crawled_at": None,
            "analyzed_at": datetime(2026, 5, 26, tzinfo=timezone.utc),
        },
    ]

    payload = market_shifts.build_market_shift_series(rows)

    assert payload["weeks"] == ["2026-05-11", "2026-05-18", "2026-05-25"]
    assert payload["summary"]["date_basis"] == {
        "posted_at": 1,
        "crawled_at": 1,
        "analyzed_at": 1,
        "unknown": 0,
    }


def test_build_market_shift_series_returns_actionable_topic_insights():
    rows = [
        {
            "title": "Backend Engineer",
            "tags": ["backend"],
            "decision": "SKIP",
            "posted_at": datetime(2026, 5, 4, tzinfo=timezone.utc),
        },
        {
            "title": "Backend Platform Engineer",
            "tags": ["backend"],
            "decision": "SKIP",
            "posted_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
        },
        {
            "title": "Backend API Engineer",
            "tags": ["backend"],
            "decision": "MAYBE",
            "posted_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
        },
        {
            "title": "Backend API Engineer",
            "tags": ["backend"],
            "decision": "SKIP",
            "posted_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
        },
        {
            "title": "Frontend Engineer",
            "tags": ["frontend"],
            "decision": "PASS",
            "posted_at": datetime(2026, 5, 4, tzinfo=timezone.utc),
        },
        {
            "title": "Frontend Developer",
            "tags": ["frontend"],
            "decision": "SKIP",
            "posted_at": datetime(2026, 5, 4, tzinfo=timezone.utc),
        },
        {
            "title": "ML Engineer",
            "tags": ["ml"],
            "decision": "PASS",
            "posted_at": datetime(2026, 5, 4, tzinfo=timezone.utc),
        },
        {
            "title": "ML Platform Engineer",
            "tags": ["ml"],
            "decision": "MAYBE",
            "posted_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
        },
    ]

    payload = market_shifts.build_market_shift_series(rows)

    assert payload["insights"]["rising_topics"][0]["topic"] == "backend"
    assert payload["insights"]["rising_topics"][0]["delta"] == 2
    assert payload["insights"]["fading_topics"][0]["topic"] == "frontend"
    assert payload["insights"]["fading_topics"][0]["delta"] == -2
    assert payload["insights"]["high_signal_topics"][0]["topic"] == "ml"
    assert payload["insights"]["noisy_topics"][0]["topic"] == "backend"


def test_extract_topics_prefers_useful_tags_and_limits_per_job():
    topics = market_shifts.extract_topics(
        {
            "title": "Senior Backend Engineer",
            "tags": '["Remote", "backend", "full-time", "Python", "Platform"]',
        }
    )

    assert topics == ["backend", "python", "platform"]


def test_extract_topics_falls_back_to_title_tokens_without_generic_words():
    topics = market_shifts.extract_topics(
        {
            "title": "Senior Full-Stack Software Engineer M/F/D - ML Platform",
            "tags": "remote, full-time",
        }
    )

    assert topics == ["ml", "platform"]


def test_extract_topics_ignores_non_scalar_tags_and_falls_back_to_title():
    topics = market_shifts.extract_topics(
        {
            "title": "Backend Python Platform Engineer",
            "tags": [{"name": "python"}, ["backend"], "remote"],
        }
    )

    assert topics == ["backend", "python", "platform"]


def test_get_market_shifts_normalizes_params_and_queries_analyzed_jobs(monkeypatch):
    seen = []

    def fake_fetch_all(query, params=()):
        seen.append((query, params))
        return [
            {
                "id": 1,
                "title": "Backend Engineer",
                "tags": ["backend"],
                "decision": "PASS",
                "posted_at": date(2026, 5, 4),
                "crawled_at": date(2026, 5, 5),
                "analyzed_at": date(2026, 5, 4),
            }
        ]

    monkeypatch.setattr(market_shifts, "TABLE", "jobs_table")
    monkeypatch.setattr(market_shifts, "fetch_all", fake_fetch_all)

    payload = market_shifts.get_market_shifts(weeks="abc", limit="bad")
    market_shifts.get_market_shifts(weeks=99, limit=99)
    market_shifts.get_market_shifts(weeks=0, limit=0)

    assert [call[1][0] for call in seen] == [12, 52, 1]
    assert "FROM jobs_table" in seen[0][0]
    assert "status = 'analyzed'" in seen[0][0]
    assert "posted_at AS market_date" in seen[0][0]
    assert "posted_at IS NOT NULL" in seen[0][0]
    assert "COALESCE(posted_at, crawled_at, analyzed_at)" not in seen[0][0]
    assert "market_date >=" in seen[0][0]
    assert (
        "market_date < date_trunc('week', CURRENT_DATE)::timestamptz + interval '1 week'"
        in seen[0][0]
    )
    assert payload["summary"]["total_jobs"] == 1
    assert payload["summary"]["topic_count"] == 1
    assert payload["summary"]["signal_jobs"] == 1
    assert payload["summary"]["date_mode"] == "posted"
    assert payload["summary"]["date_basis"]["posted_at"] == 1


def test_get_market_shifts_defaults_to_posted_only(monkeypatch):
    seen = []

    def fake_fetch_all(query, params=()):
        seen.append((query, params))
        return []

    monkeypatch.setattr(market_shifts, "TABLE", "jobs_table")
    monkeypatch.setattr(market_shifts, "fetch_all", fake_fetch_all)

    payload = market_shifts.get_market_shifts(weeks=12, limit=20)

    assert seen[0][1] == (12,)
    assert "posted_at AS market_date" in seen[0][0]
    assert "posted_at IS NOT NULL" in seen[0][0]
    assert "COALESCE(posted_at, crawled_at, analyzed_at)" not in seen[0][0]
    assert payload["summary"]["date_mode"] == "posted"


def test_get_market_shifts_can_include_fallback_dates(monkeypatch):
    seen = []

    def fake_fetch_all(query, params=()):
        seen.append((query, params))
        return []

    monkeypatch.setattr(market_shifts, "TABLE", "jobs_table")
    monkeypatch.setattr(market_shifts, "fetch_all", fake_fetch_all)

    payload = market_shifts.get_market_shifts(weeks=12, limit=20, date_mode="fallback")

    assert "COALESCE(posted_at, crawled_at, analyzed_at) AS market_date" in seen[0][0]
    assert payload["summary"]["date_mode"] == "fallback"
