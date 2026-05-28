from pathlib import Path

from fastapi.testclient import TestClient

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


def test_analytics_api_scoring_returns_empty_shape():
    response = TestClient(app).get("/api/analytics/scoring")

    assert response.status_code == 200
    assert response.json() == {
        "summary": {},
        "buckets": [],
        "decisions": [],
        "user_statuses": [],
        "mismatches": {
            "high_score_dismissed": [],
            "low_score_applied": [],
            "pending_review": [],
        },
    }


def test_analytics_api_funnel_returns_empty_shape():
    response = TestClient(app).get("/api/analytics/funnel")

    assert response.status_code == 200
    assert response.json() == {
        "summary": {},
        "weeks": [],
        "stuck_jobs": [],
    }


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
    assert ".analytics-shell" in ANALYTICS_CSS.read_text(encoding="utf-8")
