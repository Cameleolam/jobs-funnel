from pathlib import Path

from fastapi.testclient import TestClient

from ui.routes import analytics
from ui.server import app


ANALYTICS_JS = Path("ui/static/analytics.js")
ANALYTICS_CSS = Path("ui/static/analytics.css")


def test_analytics_page_renders_shell():
    response = TestClient(app).get("/analytics")

    assert response.status_code == 200
    assert "Insights" in response.text
    assert 'href="/static/analytics.css"' in response.text
    assert 'src="/static/analytics.js"' in response.text
    assert 'id="analytics-act"' in response.text
    assert 'id="analytics-learn"' in response.text
    assert 'id="analytics-improve"' in response.text
    assert 'id="analytics-market"' in response.text
    assert 'data-analytics-view="all"' in response.text
    assert 'data-analytics-view-button="all"' in response.text
    assert 'data-analytics-view-button="act"' in response.text
    assert 'data-analytics-view-button="learn"' in response.text
    assert 'data-analytics-view-button="improve"' in response.text
    assert 'data-analytics-view-button="market"' in response.text
    assert 'data-market-filter' in response.text
    assert 'data-market-window' in response.text
    assert 'data-market-topic-limit' in response.text
    assert 'data-market-date-mode' in response.text
    assert 'data-analytics-window' not in response.text
    assert 'data-analytics-topic-limit' not in response.text
    assert "Act Today" in response.text
    assert "Learn From Decisions" in response.text
    assert "Improve The Funnel" in response.text
    assert "Market Signals" in response.text


def test_analytics_api_scoring_returns_service_payload(monkeypatch):
    payload = {
        "summary": {
            "total": 1,
            "applied": 1,
            "dismissed": 0,
            "pending_review": 0,
            "needs_human_review": 0,
            "low_confidence": 0,
            "high_score_dismissed": 0,
            "low_score_applied": 1,
        },
        "buckets": [
            {
                "bucket": "3-5",
                "total": 1,
                "applied": 1,
                "dismissed": 0,
                "application_rate": 1.0,
                "dismissed_rate": 0.0,
            }
        ],
        "decisions": [{"decision": "recommended", "count": 1}],
        "user_statuses": [{"user_status": "applied", "count": 1}],
        "mismatches": {
            "high_score_dismissed": [],
            "low_score_applied": [
                {
                    "id": 12,
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "fit_score": 4,
                    "decision": "recommended",
                    "user_status": "applied",
                    "job_url": "/jobs/12/view",
                }
            ],
            "pending_review": [],
        },
        "action_queue": {"apply_targets": [], "review_candidates": []},
        "source_quality": [],
    }
    monkeypatch.setattr(
        analytics.scoring_insights,
        "get_scoring_summary",
        lambda: payload,
    )

    response = TestClient(app).get("/api/analytics/scoring")

    assert response.status_code == 200
    assert response.json() == payload


def test_analytics_api_funnel_returns_service_payload(monkeypatch):
    payload = {
        "summary": {
            "tracked_jobs": 2,
            "applied": 1,
            "in_process": 1,
            "rejected": 0,
            "closed": 0,
            "interviews": 1,
            "avg_days_to_close": None,
        },
        "weeks": [
            {
                "week": "2026-05-04",
                "application": 1,
                "contact": 0,
                "interview": 1,
                "task": 0,
                "outcome": 0,
                "note": 0,
                "review_decision": 0,
                "total": 2,
            }
        ],
        "stuck_jobs": [],
    }
    seen = {}
    monkeypatch.setattr(
        analytics.funnel_analytics,
        "get_funnel_summary",
        lambda weeks=12: seen.setdefault("payload", (weeks, payload))[1],
    )

    response = TestClient(app).get("/api/analytics/funnel?weeks=12")

    assert response.status_code == 200
    assert seen["payload"][0] == "12"
    assert response.json() == payload


def test_analytics_api_funnel_tolerates_invalid_weeks(monkeypatch):
    payload = {
        "summary": {},
        "weeks": [],
        "stuck_jobs": [],
    }
    seen = {}
    monkeypatch.setattr(
        analytics.funnel_analytics,
        "get_funnel_summary",
        lambda weeks=12: seen.setdefault("payload", (weeks, payload))[1],
    )

    response = TestClient(app).get("/api/analytics/funnel?weeks=abc")

    assert response.status_code == 200
    assert seen["payload"][0] == "abc"
    assert response.json() == payload


def test_analytics_api_market_shifts_returns_service_payload(monkeypatch):
    payload = {
        "weeks": ["2026-05-04"],
        "topics": [
            {
                "topic": "backend",
                "total": 1,
                "signal_total": 1,
                "weeks": [{"week": "2026-05-04", "count": 1, "signal_count": 1}],
            }
        ],
        "summary": {"total_jobs": 1, "topic_count": 1, "signal_jobs": 1},
        "insights": {
            "rising_topics": [],
            "fading_topics": [],
            "high_signal_topics": [],
            "noisy_topics": [],
        },
    }
    seen = {}
    monkeypatch.setattr(
        analytics.market_shifts,
        "get_market_shifts",
        lambda weeks=12, limit=20, date_mode="posted": seen.setdefault(
            "payload",
            (weeks, limit, date_mode, payload),
        )[3],
    )

    response = TestClient(app).get(
        "/api/analytics/market-shifts?weeks=12&limit=20&date_mode=fallback"
    )

    assert response.status_code == 200
    assert seen["payload"][:3] == ("12", "20", "fallback")
    assert response.json() == payload


def test_analytics_static_assets_are_served_and_define_shell_hooks():
    client = TestClient(app)

    css_response = client.get("/static/analytics.css")
    js_response = client.get("/static/analytics.js")

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert js_response.status_code == 200
    assert "renderEmptyState" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderActPanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderLearnPanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderImprovePanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderMarketPanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderInsightCards" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "job.job_url" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "data-market-window" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "data-market-date-mode" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "data-analytics-view-button" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "Apply targets" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert ".analytics-shell" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".analytics-shell.view-act" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".analytics-insights" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".insights-job-list" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".source-quality-list" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".funnel-timeline" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".market-heatmap" in ANALYTICS_CSS.read_text(encoding="utf-8")
