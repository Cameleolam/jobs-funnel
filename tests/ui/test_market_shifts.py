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

    assert payload == {
        "weeks": ["2026-05-04", "2026-05-11"],
        "topics": [
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
        ],
        "summary": {"total_jobs": 3, "topic_count": 4, "signal_jobs": 2},
    }


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
    assert "analyzed_at >=" in seen[0][0]
    assert payload["summary"] == {"total_jobs": 1, "topic_count": 1, "signal_jobs": 1}
