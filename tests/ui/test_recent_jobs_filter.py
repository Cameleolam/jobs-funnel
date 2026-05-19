"""Tests for the default recent-jobs filter."""

from fastapi.testclient import TestClient

import ui.config as ui_config
import ui.server as srv
from ui.routes import jobs as jobs_routes


RECENT_CLAUSE = "crawled_at >= NOW() - INTERVAL '10 days'"


def _stub_stats(monkeypatch):
    monkeypatch.setattr(
        jobs_routes.stats_service,
        "get_stats",
        lambda: {
            "total": 0,
            "PASS": 0,
            "MAYBE": 0,
            "SKIP": 0,
            "pending": 0,
            "interested": 0,
            "applied": 0,
            "dismissed": 0,
            "error": 0,
            "dead": 0,
            "awaiting_embedding": 0,
        },
    )


def test_default_jobs_filter_limits_to_last_10_days():
    where, params = jobs_routes.build_job_filter()

    assert RECENT_CLAUSE in where
    assert params == [0, 10]


def test_recent_only_false_removes_last_10_days_filter():
    where, params = jobs_routes.build_job_filter(recent_only=False)

    assert RECENT_CLAUSE not in where
    assert params == [0, 10]


def test_special_views_ignore_recent_only_filter(monkeypatch):
    monkeypatch.setattr(jobs_routes.schema, "HAS_HUMAN_REVIEW_COLUMNS", True)

    for view in ("review", "error", "dead", "failed", "duplicates"):
        where, _ = jobs_routes.build_job_filter(view=view, recent_only=True)
        assert RECENT_CLAUSE not in where


def test_jobs_template_has_recent_only_checked_by_default():
    html = (ui_config.TEMPLATES_DIR / "jobs.html").read_text(encoding="utf-8")

    assert 'name="recent_only"' in html
    assert "Last 10 days" in html
    assert "checked" in html


def test_review_queue_shortcut_state_loads_review_jobs(monkeypatch):
    _stub_stats(monkeypatch)

    response = TestClient(srv.app).get("/?view=review")

    assert response.status_code == 200
    assert '<option value="review" selected>Review queue</option>' in response.text
    assert 'hx-get="/jobs?' in response.text
    assert "view=review" in response.text


def test_jobs_page_defaults_recent_and_hide_rejected_on(monkeypatch):
    _stub_stats(monkeypatch)

    response = TestClient(srv.app).get("/")

    assert response.status_code == 200
    assert 'name="recent_only" value="true" checked' in response.text
    assert 'name="hide_rejected" value="true" checked' in response.text


def test_jobs_page_preserves_false_checkbox_state(monkeypatch):
    _stub_stats(monkeypatch)

    response = TestClient(srv.app).get("/?recent_only=false&hide_rejected=false")

    assert response.status_code == 200
    assert 'name="recent_only" value="true" checked' not in response.text
    assert 'name="hide_rejected" value="true" checked' not in response.text
