"""Tests for Phase 3 calibration retrieval."""
from unittest.mock import MagicMock

import pytest

import scripts.retrieval as retrieval


@pytest.fixture(autouse=True)
def _isolate_calibration_settings(monkeypatch):
    retrieval.calibration_settings.reset_cache()
    monkeypatch.setattr(
        retrieval.calibration_settings.db,
        "get_conn",
        MagicMock(side_effect=RuntimeError("no settings db")),
    )
    yield
    retrieval.calibration_settings.reset_cache()


def test_format_anchor_prefers_user_note_and_marks_interview():
    anchor = {
        "id": 7,
        "title": "Backend Engineer",
        "company": "Acme",
        "fit_score": 82,
        "calibration_label": "applied",
        "notes": "Interview invite after focused backend pitch.",
        "reasoning": "Claude fallback should not be used.",
        "reached_interview": True,
        "received_offer": False,
    }

    text = retrieval.format_anchor(anchor, index=1)

    assert '1. "Backend Engineer @ Acme"' in text
    assert "Score: 82 -> applied -> reached interview" in text
    assert "Your note: Interview invite after focused backend pitch." in text
    assert "Claude fallback" not in text


def test_format_anchor_falls_back_to_reasoning_and_caps_text():
    anchor = {
        "id": 8,
        "title": "Senior Data Engineer",
        "company": "BigCorp",
        "fit_score": 55,
        "calibration_label": "dismissed",
        "notes": "",
        "reasoning": "x" * 260,
        "reached_interview": False,
        "received_offer": False,
    }

    text = retrieval.format_anchor(anchor, index=2)

    assert '2. "Senior Data Engineer @ BigCorp"' in text
    assert "Score: 55 -> dismissed" in text
    assert "Your prior reasoning: " in text
    assert ("x" * 220) not in text


def test_format_calibration_block_returns_empty_for_no_anchors():
    assert retrieval.format_calibration_block([]) == ""


def test_format_calibration_block_includes_header_and_numbered_anchors():
    anchors = [
        {"id": 1, "title": "A", "company": "C", "fit_score": 90, "calibration_label": "offer", "notes": "great", "reasoning": "", "reached_interview": True, "received_offer": True},
        {"id": 2, "title": "B", "company": "D", "fit_score": 20, "calibration_label": "dismissed", "notes": "", "reasoning": "weak", "reached_interview": False, "received_offer": False},
    ]

    block = retrieval.format_calibration_block(anchors)

    assert block.startswith("CALIBRATION - here's how you handled similar jobs in the past.")
    assert '1. "A @ C"' in block
    assert '2. "B @ D"' in block
    assert "received offer" in block


def test_merge_batch_anchors_dedupes_and_caps_by_weighted_score(monkeypatch):
    monkeypatch.setattr(retrieval, "calibration_k_batch", lambda: 2)
    anchors = [
        [{"id": 1, "weighted_score": 0.2}, {"id": 2, "weighted_score": 0.9}],
        [{"id": 1, "weighted_score": 0.8}, {"id": 3, "weighted_score": 0.7}],
    ]

    merged = retrieval.merge_batch_anchors(anchors)

    assert [a["id"] for a in merged] == [2, 1]
    assert merged[1]["weighted_score"] == 0.8


def test_retrieval_weight_accessor_uses_active_settings(monkeypatch):
    monkeypatch.setattr(
        retrieval.calibration_settings,
        "retrieval_weights",
        lambda: {
            "offer": 2.0,
            "interview": 1.8,
            "applied": 1.4,
            "dismiss_note": 1.3,
            "dismiss": 0.9,
            "interested": 0.5,
        },
    )

    assert retrieval.weights()["offer"] == 2.0
    assert retrieval.weights()["interested"] == 0.5


def _fake_conn(fetchone_rows=None, fetchall_rows=None):
    cur = MagicMock()
    one_rows = list(fetchone_rows or [])
    all_rows = list(fetchall_rows or [])
    cur.fetchone.side_effect = lambda: one_rows.pop(0) if one_rows else None
    cur.fetchall.side_effect = lambda: all_rows.pop(0) if all_rows else []
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_retrieve_returns_empty_when_embedding_fails(monkeypatch):
    monkeypatch.setattr(retrieval.embed_mod, "embed", MagicMock(side_effect=RuntimeError("ollama down")))
    get_conn = MagicMock()
    monkeypatch.setattr(retrieval.db, "get_vector_conn", get_conn)

    assert retrieval.retrieve_similar_decisions({"title": "Backend"}) == []
    get_conn.assert_not_called()


def test_retrieve_returns_empty_when_database_fails(monkeypatch):
    monkeypatch.setattr(retrieval.embed_mod, "embed", lambda text: [0.1] * 1024)
    monkeypatch.setattr(retrieval.embed_mod, "text_for_calibration", lambda job: "calibration text")
    monkeypatch.setattr(retrieval.db, "get_vector_conn", MagicMock(side_effect=RuntimeError("db down")))

    assert retrieval.retrieve_similar_decisions({"title": "Backend"}, k=3) == []


def test_retrieve_returns_empty_when_pool_below_minimum(monkeypatch):
    conn, cur = _fake_conn(fetchone_rows=[{"n": 2}])
    monkeypatch.setattr(retrieval.embed_mod, "embed", lambda text: [0.1] * 1024)
    monkeypatch.setattr(retrieval.embed_mod, "text_for_calibration", lambda job: "calibration text")
    monkeypatch.setattr(retrieval.db, "get_vector_conn", lambda: conn)
    monkeypatch.setattr(retrieval, "calibration_min_pool", lambda: 3)

    assert retrieval.retrieve_similar_decisions({"title": "Backend"}, k=3) == []
    assert cur.execute.call_count == 1
    conn.close.assert_called_once_with()


def test_retrieve_queries_weighted_candidates_from_active_tables(monkeypatch):
    rows = [{
        "id": 3,
        "title": "Backend",
        "company": "Acme",
        "fit_score": 82,
        "decision": "APPLY",
        "reasoning": "good backend match",
        "notes": "got interview",
        "user_status": "applied",
        "seniority_level": "mid",
        "calibration_label": "applied",
        "reached_interview": True,
        "received_offer": False,
        "similarity": 0.91,
        "weighted_score": 1.09,
    }]
    conn, cur = _fake_conn(fetchone_rows=[{"n": 4}], fetchall_rows=[rows])
    monkeypatch.setattr(retrieval.embed_mod, "embed", lambda text: [0.1] * 1024)
    monkeypatch.setattr(retrieval.embed_mod, "text_for_calibration", lambda job: "calibration text")
    monkeypatch.setattr(retrieval.db, "get_vector_conn", lambda: conn)
    monkeypatch.setattr(retrieval.db, "table_name", lambda: "jobs_test")
    monkeypatch.setattr(retrieval.db, "events_table_name", lambda: "jobs_test_events")

    out = retrieval.retrieve_similar_decisions({"title": "Backend", "seniority_level": "mid"}, k=2)

    assert out == rows
    pool_sql = cur.execute.call_args_list[0].args[0]
    retrieval_sql, params = cur.execute.call_args_list[1].args
    assert "FROM jobs_test" in pool_sql
    assert "FROM jobs_test_events" in retrieval_sql
    assert "embedding_calibration <=> %s::vector" in retrieval_sql
    assert "LIKE '%%offer%%'" in retrieval_sql
    assert "weighted_score DESC" in retrieval_sql
    assert params[-2:] == ("mid", 2)
