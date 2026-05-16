"""Tests for the default recent-jobs filter."""

import ui.server as srv


RECENT_CLAUSE = "crawled_at >= NOW() - INTERVAL '10 days'"


def test_default_jobs_filter_limits_to_last_10_days():
    where, params = srv.build_job_filter()

    assert RECENT_CLAUSE in where
    assert params == [0, 10]


def test_recent_only_false_removes_last_10_days_filter():
    where, params = srv.build_job_filter(recent_only=False)

    assert RECENT_CLAUSE not in where
    assert params == [0, 10]


def test_special_views_ignore_recent_only_filter(monkeypatch):
    monkeypatch.setattr(srv, "HAS_HUMAN_REVIEW_COLUMNS", True)

    for view in ("review", "error", "dead", "failed", "duplicates"):
        where, _ = srv.build_job_filter(view=view, recent_only=True)
        assert RECENT_CLAUSE not in where


def test_jobs_template_has_recent_only_checked_by_default():
    html = (srv.TEMPLATES_DIR / "jobs.html").read_text(encoding="utf-8")

    assert 'name="recent_only"' in html
    assert "Last 10 days" in html
    assert "checked" in html
