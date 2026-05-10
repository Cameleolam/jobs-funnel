"""Tests for scripts/dedup.py."""
from unittest.mock import MagicMock

import scripts.dedup as dedup


def test_classify_similarity_routes_certain_duplicate():
    assert dedup.classify_similarity(0.95) == "vector_certain"
    assert dedup.classify_similarity(0.99) == "vector_certain"


def test_classify_similarity_routes_clear_non_duplicate():
    assert dedup.classify_similarity(0.10) == "vector_clear"
    assert dedup.classify_similarity(0.849) == "vector_clear"


def test_classify_similarity_routes_review_band():
    assert dedup.classify_similarity(0.85) == "claude_review"
    assert dedup.classify_similarity(0.949) == "claude_review"


def test_classify_similarity_rejects_missing_similarity():
    assert dedup.classify_similarity(None) == "no_match"


def _fake_conn(fetchone_rows):
    cur = MagicMock()
    rows = list(fetchone_rows)
    cur.fetchone.side_effect = lambda: rows.pop(0) if rows else None
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_find_duplicate_by_id_returns_no_embedding_when_new_job_has_no_vector(monkeypatch):
    conn, cur = _fake_conn([
        {"id": 10, "title": "A", "company": "C", "location": "Berlin", "embedding": None},
    ])
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    decision = dedup.find_duplicate_by_id(10, table="jobs_test")

    assert decision.new_id == 10
    assert decision.existing_id is None
    assert decision.decision_path == "no_embedding"
    assert cur.execute.call_count == 1
    conn.close.assert_called_once_with()


def test_find_duplicate_by_id_marks_vector_certain_duplicate(monkeypatch):
    conn, cur = _fake_conn([
        {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin", "embedding": [0.1] * 1024},
        {"id": 9, "title": "Backend Engineer", "company": "Acme", "location": "Berlin", "similarity": 0.97},
    ])
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    decision = dedup.find_duplicate_by_id(10, table="jobs_test")

    assert decision.existing_id == 9
    assert decision.decision_path == "vector_certain"
    assert decision.confidence == "high"
    assert "embedding <=>" in cur.execute.call_args_list[1].args[0]
    assert "make_interval(days => %s)" in cur.execute.call_args_list[1].args[0]


def test_find_duplicate_by_id_returns_clear_when_similarity_below_review(monkeypatch):
    conn, cur = _fake_conn([
        {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin", "embedding": [0.1] * 1024},
        {"id": 8, "title": "Designer", "company": "Acme", "location": "Berlin", "similarity": 0.70},
    ])
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    decision = dedup.find_duplicate_by_id(10, table="jobs_test")

    assert decision.existing_id is None
    assert decision.decision_path == "vector_clear"
    assert decision.similarity == 0.70


def test_claude_review_marks_duplicate_on_true_response(monkeypatch):
    job = {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin"}
    match = {"id": 9, "title": "Backend Engineer", "company": "Acme", "location": "Berlin"}
    fake = MagicMock(returncode=0, stdout='{"result":"{\\"duplicate\\": true, \\"reason\\": \\"same role\\"}"}', stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)

    decision = dedup._claude_review_decision(job, match, 0.90)

    assert decision.existing_id == 9
    assert decision.decision_path == "claude_dup"
    assert decision.confidence == "medium"


def test_claude_review_returns_clear_on_false_response(monkeypatch):
    job = {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin"}
    match = {"id": 9, "title": "Frontend", "company": "Acme", "location": "Berlin"}
    fake = MagicMock(returncode=0, stdout='{"result":"{\\"duplicate\\": false, \\"reason\\": \\"different role\\"}"}', stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)

    decision = dedup._claude_review_decision(job, match, 0.90)

    assert decision.existing_id is None
    assert decision.decision_path == "claude_clear"


def test_claude_review_fails_closed_on_bad_response(monkeypatch):
    job = {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin"}
    match = {"id": 9, "title": "Backend Engineer", "company": "Acme", "location": "Berlin"}
    fake = MagicMock(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)

    decision = dedup._claude_review_decision(job, match, 0.90)

    assert decision.existing_id is None
    assert decision.decision_path == "claude_error"


def test_claude_review_fails_closed_on_process_launch_os_error(monkeypatch):
    job = {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin"}
    match = {"id": 9, "title": "Backend Engineer", "company": "Acme", "location": "Berlin"}

    def raise_permission_error(*args, **kwargs):
        raise PermissionError("claude shim is not executable")

    monkeypatch.setattr("subprocess.run", raise_permission_error)

    decision = dedup._claude_review_decision(job, match, 0.90)

    assert decision.existing_id is None
    assert decision.decision_path == "claude_error"


def test_claude_review_fails_closed_on_timeout(monkeypatch):
    job = {"id": 10, "title": "Backend", "company": "Acme", "location": "Berlin"}
    match = {"id": 9, "title": "Backend Engineer", "company": "Acme", "location": "Berlin"}

    def raise_timeout(*args, **kwargs):
        raise dedup.subprocess.TimeoutExpired(cmd="claude", timeout=120)

    monkeypatch.setattr("subprocess.run", raise_timeout)

    decision = dedup._claude_review_decision(job, match, 0.90)

    assert decision.existing_id is None
    assert decision.decision_path == "claude_error"
