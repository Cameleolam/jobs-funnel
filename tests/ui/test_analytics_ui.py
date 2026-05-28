from pathlib import Path

from fastapi.testclient import TestClient

from ui.routes import analytics
from ui.server import app


ANALYTICS_JS = Path("ui/static/analytics.js")
ANALYTICS_CSS = Path("ui/static/analytics.css")


def test_analytics_page_renders_shell():
    response = TestClient(app).get("/analytics")

    assert response.status_code == 200
    assert "Analytics" in response.text
    assert 'href="/static/analytics.css"' in response.text
    assert 'src="/static/analytics.js"' in response.text
    assert 'id="analytics-scoring"' in response.text
    assert 'id="analytics-funnel"' in response.text
    assert 'id="analytics-market"' in response.text
    assert "Scoring" in response.text
    assert "Funnel" in response.text
    assert "Market" in response.text


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
                }
            ],
            "pending_review": [],
        },
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
                "decision": 0,
                "note": 0,
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


def test_analytics_api_market_shifts_returns_empty_shape():
    response = TestClient(app).get("/api/analytics/market-shifts")

    assert response.status_code == 200
    assert response.json() == {
        "weeks": [],
        "topics": [],
        "summary": {},
    }


def test_analytics_static_assets_are_served_and_define_shell_hooks():
    client = TestClient(app)

    css_response = client.get("/static/analytics.css")
    js_response = client.get("/static/analytics.js")

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert js_response.status_code == 200
    assert "renderEmptyState" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderScoringPanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert "renderFunnelPanel" in ANALYTICS_JS.read_text(encoding="utf-8")
    assert ".analytics-shell" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".scoring-bucket" in ANALYTICS_CSS.read_text(encoding="utf-8")
    assert ".funnel-timeline" in ANALYTICS_CSS.read_text(encoding="utf-8")
