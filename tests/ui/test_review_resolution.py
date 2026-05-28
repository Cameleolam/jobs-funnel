"""Tests for Phase 5 human review resolution."""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import ui.config as ui_config
import ui.server as srv
from ui.rendering import templates
from ui.routes import jobs as jobs_routes


@contextmanager
def _fake_get_db(conn):
    yield conn


def _fake_conn(fetch_rows):
    cur = MagicMock()
    rows = list(fetch_rows)
    cur.fetchone.side_effect = lambda: rows.pop(0) if rows else None
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def _patch_row_render(monkeypatch):
    def fake_render(request, name, ctx=None):
        assert name == "partials/job_row_single.html"
        job = (ctx or {})["job"]
        return HTMLResponse(f"row:{job['id']}:{job['decision']}:{job['user_status']}")

    monkeypatch.setattr(jobs_routes, "render", fake_render)


def test_review_action_map_is_explicit():
    assert jobs_routes.REVIEW_ACTIONS == {
        "apply_target": {
            "decision": "PASS",
            "user_status": "interested",
            "label": "Reviewed: apply target",
        },
        "maybe": {
            "decision": "MAYBE",
            "user_status": "interested",
            "label": "Reviewed: maybe",
        },
        "skip": {
            "decision": "SKIP",
            "user_status": "dismissed",
            "label": "Reviewed: skip",
        },
    }


def test_review_notes_value_preserves_existing_notes_on_blank_submission():
    assert jobs_routes._review_notes_value("Keep this", "   ") == "Keep this"
    assert jobs_routes._review_notes_value(None, "   ") is None
    assert jobs_routes._review_notes_value("Old", "  New reason  ") == "New reason"


def test_review_order_prioritizes_high_score_then_recent_analysis():
    assert jobs_routes.build_order_clause("company", "ASC", "review") == (
        "COALESCE(fit_score, 0) DESC, analyzed_at DESC NULLS LAST, id DESC"
    )


def test_default_order_keeps_user_sort():
    assert jobs_routes.build_order_clause("company", "ASC", "") == "company ASC, id ASC"


def test_review_resolution_updates_job_and_inserts_decision_event(monkeypatch):
    client = TestClient(srv.app)
    _patch_row_render(monkeypatch)
    monkeypatch.setattr(jobs_routes.schema, "HAS_HUMAN_REVIEW_COLUMNS", True)

    updated_job = {"id": 42, "decision": "PASS", "user_status": "interested"}
    conn, cur = _fake_conn([{"id": 42, "notes": "old note"}, updated_job])
    monkeypatch.setattr(jobs_routes, "get_db", lambda: _fake_get_db(conn))

    response = client.patch(
        "/jobs/42/review",
        data={"review_action": "apply_target", "notes": "Worth applying"},
    )

    assert response.status_code == 200
    assert response.text == "row:42:PASS:interested"
    assert cur.execute.call_count == 4

    update_sql, update_params = cur.execute.call_args_list[1].args
    assert "UPDATE" in update_sql
    assert "needs_human_review = FALSE" in update_sql
    assert "fit_score" not in update_sql
    assert "base_fit_score" not in update_sql
    assert "reasoning" not in update_sql
    assert "scoring_provider" not in update_sql
    assert "review_provider" not in update_sql
    assert update_params == ("PASS", "interested", "Worth applying", 42)

    insert_sql, insert_params = cur.execute.call_args_list[2].args
    assert "INSERT INTO" in insert_sql
    assert "kind, label, notes" in insert_sql
    assert insert_params == (42, "Reviewed: apply target", "Worth applying")


def test_review_resolution_preserves_existing_notes_when_submitted_blank(monkeypatch):
    client = TestClient(srv.app)
    _patch_row_render(monkeypatch)
    monkeypatch.setattr(jobs_routes.schema, "HAS_HUMAN_REVIEW_COLUMNS", True)

    updated_job = {"id": 77, "decision": "SKIP", "user_status": "dismissed"}
    conn, cur = _fake_conn([{"id": 77, "notes": "Keep this note"}, updated_job])
    monkeypatch.setattr(jobs_routes, "get_db", lambda: _fake_get_db(conn))

    response = client.patch(
        "/jobs/77/review",
        data={"review_action": "skip", "notes": "   "},
    )

    assert response.status_code == 200
    update_params = cur.execute.call_args_list[1].args[1]
    insert_params = cur.execute.call_args_list[2].args[1]
    assert update_params == ("SKIP", "dismissed", "Keep this note", 77)
    assert insert_params == (77, "Reviewed: skip", None)


def test_review_resolution_skips_missing_optional_column_assignment(monkeypatch):
    client = TestClient(srv.app)
    _patch_row_render(monkeypatch)
    monkeypatch.setattr(jobs_routes.schema, "HAS_HUMAN_REVIEW_COLUMNS", False)

    updated_job = {"id": 88, "decision": "MAYBE", "user_status": "interested"}
    conn, cur = _fake_conn([{"id": 88, "notes": None}, updated_job])
    monkeypatch.setattr(jobs_routes, "get_db", lambda: _fake_get_db(conn))

    response = client.patch(
        "/jobs/88/review",
        data={"review_action": "maybe", "notes": ""},
    )

    assert response.status_code == 200
    update_sql = cur.execute.call_args_list[1].args[0]
    assert "needs_human_review" not in update_sql


def test_review_resolution_rejects_unknown_action_before_db(monkeypatch):
    client = TestClient(srv.app)
    get_db = MagicMock()
    monkeypatch.setattr(jobs_routes, "get_db", get_db)

    response = client.patch(
        "/jobs/42/review",
        data={"review_action": "bad_action", "notes": "x"},
    )

    assert response.status_code == 400
    assert response.text == "Invalid review action"
    get_db.assert_not_called()


def test_review_resolution_returns_404_for_missing_job(monkeypatch):
    client = TestClient(srv.app)
    conn, cur = _fake_conn([None])
    monkeypatch.setattr(jobs_routes, "get_db", lambda: _fake_get_db(conn))

    response = client.patch(
        "/jobs/404/review",
        data={"review_action": "skip", "notes": "not relevant"},
    )

    assert response.status_code == 404
    assert response.text == "Job not found"
    assert cur.execute.call_count == 1


def test_jobs_view_selector_exposes_review_queue():
    html = (ui_config.TEMPLATES_DIR / "jobs.html").read_text(encoding="utf-8")
    assert 'value="review"' in html
    assert "Review queue</option>" in html


def _review_job_row():
    return {
        "id": 42,
        "url": "https://example.com/job/42",
        "title": "Automation Engineer",
        "company": "Acme",
        "location": "Remote EU",
        "source": "manual",
        "status": "analyzed",
        "decision": "pending_review",
        "fit_score": 5,
        "base_fit_score": 5,
        "base_decision": "MAYBE",
        "scoring_provider": "codex_gpt55_high",
        "scoring_model": "gpt-5.5",
        "review_provider": "claude_sonnet",
        "review_model": "claude-sonnet-4-6",
        "review_error": None,
        "needs_human_review": True,
        "explanation": "Score stayed in the review band after critique.",
        "confidence": "medium",
        "critique_count": 1,
        "reasoning": "Good automation match but unclear location.",
        "hard_blockers": [],
        "strong_matches": ["Python", "automation"],
        "soft_gaps": ["unclear location"],
        "tags": [],
        "priority_notes": None,
        "notes": "Ask about EU remote.",
        "possible_duplicate_of": None,
        "duplicate_confirmed": None,
        "crawled_at": None,
        "analyzed_at": None,
        "posted_at": None,
        "employment_type": None,
        "seniority_level": None,
        "start_date": None,
        "description": "Build internal automation.",
    }


def test_job_detail_renders_review_resolution_controls(monkeypatch):
    client = TestClient(srv.app)
    monkeypatch.setattr(jobs_routes, "fetch_one", lambda query, params=(): _review_job_row())

    response = client.get("/jobs/42")

    assert response.status_code == 200
    assert 'hx-patch="/jobs/42/review"' in response.text
    assert 'name="review_action" value="apply_target"' in response.text
    assert 'name="review_action" value="maybe"' in response.text
    assert 'name="review_action" value="skip"' in response.text
    assert "Score stayed in the review band after critique." in response.text
    assert "codex_gpt55_high" in response.text
    assert "claude_sonnet" in response.text
    assert "Ask about EU remote." in response.text


def test_job_view_renders_full_page(monkeypatch):
    client = TestClient(srv.app)
    monkeypatch.setattr(jobs_routes, "fetch_one", lambda query, params=(): _review_job_row())

    response = client.get("/jobs/42/view")

    assert response.status_code == 200
    assert "Jobs Funnel" in response.text
    assert "Ask about EU remote." in response.text
    assert "Back to jobs" in response.text
    assert "Close</button>" not in response.text
    assert 'hx-target="#row-' not in response.text


def test_job_row_renders_review_state():
    html = templates.get_template("partials/job_row_single.html").render(
        request={},
        now=datetime.now().astimezone(),
        job={
            **_review_job_row(),
            "awaiting_embedding": False,
            "scored_uncalibrated": False,
            "tracked_at": None,
            "error_code": None,
            "error": None,
            "retry_count": 0,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": "EUR",
            "remote": True,
            "likely_english": True,
            "staffing_agency": False,
            "geo_mismatch": False,
            "user_status": None,
        },
    )

    assert "status-review" in html
    assert "badge-review" in html
    assert ">REVIEW<" in html
