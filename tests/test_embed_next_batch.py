"""Tests for scripts/embed_next_batch.py."""
import json
from unittest.mock import MagicMock

import pytest

import scripts.embed_next_batch as eb
from scripts import embed as embed_mod


def _fake_conn(rows_by_query=None):
    rows_by_query = rows_by_query or {}
    cur = MagicMock()
    state = {"last_query": ""}

    def execute(q, params=None):
        state["last_query"] = q

    def fetchall():
        for sub, rows in rows_by_query.items():
            if sub in state["last_query"]:
                return rows
        return []

    def fetchone():
        if "SELECT EXISTS" in state["last_query"] and "SELECT EXISTS" in rows_by_query:
            return rows_by_query["SELECT EXISTS"]
        for sub, row in rows_by_query.items():
            if sub in state["last_query"]:
                return row
        return {"exists": False}

    cur.execute.side_effect = execute
    cur.fetchall.side_effect = fetchall
    cur.fetchone.side_effect = fetchone
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.rollback = MagicMock()
    conn.close = MagicMock()
    return conn, cur


def _job(job_id):
    return {
        "id": job_id,
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Python role",
        "remote": False,
        "seniority_level": "mid",
        "employment_type": "full-time",
        "likely_english": True,
    }


def test_cap_remaining_zero_short_circuits_without_db(monkeypatch):
    monkeypatch.setattr(
        "scripts.db.get_vector_conn",
        lambda: pytest.fail("DB should not be opened"),
    )

    summary = eb.run(["--limit", "8", "--cap-remaining", "0"])

    assert summary["processed"] == 0
    assert summary["failed"] == 0
    assert summary["attempted"] == 0
    assert summary["has_more"] is True
    assert summary["capped"] is True
    assert summary["batch_size"] == 0
    assert isinstance(summary["batch_id"], str)


def test_successful_rows_are_embedded_and_counted(monkeypatch):
    rows = [_job(1), _job(2)]
    conn, cur = _fake_conn({
        "embedding IS NULL": rows,
        "SELECT EXISTS": {"exists": False},
    })
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)
    monkeypatch.setattr(embed_mod, "embed", lambda text: [0.1] * 1024)

    summary = eb.run(["--limit", "8", "--cap-remaining", "8"])

    assert summary["processed"] == 2
    assert summary["failed"] == 0
    assert summary["attempted"] == 2
    assert summary["has_more"] is False
    assert summary["model"] == embed_mod.MODEL
    assert any("embedded_at = NOW()" in c.args[0] for c in cur.execute.call_args_list)
    assert conn.autocommit is True
    conn.close.assert_called_once()


def test_selector_prioritizes_unembedded_pending_jobs(monkeypatch):
    rows = [_job(1)]
    conn, cur = _fake_conn({
        "status IN ('pending', 'error')": rows,
        "SELECT EXISTS": {"exists": False},
    })
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)
    monkeypatch.setattr(embed_mod, "embed", lambda text: [0.1] * 1024)

    eb.run(["--limit", "8", "--cap-remaining", "8"])

    select_sql = cur.execute.call_args_list[0].args[0]
    assert "status IN ('pending', 'error')" in select_sql
    assert "retry_count < 3" in select_sql
    assert "embedding_calibration IS NULL" in select_sql


def test_embed_errors_increment_failures_and_continue(monkeypatch):
    rows = [_job(1), _job(2)]
    conn, cur = _fake_conn({
        "embedding IS NULL": rows,
        "SELECT EXISTS": {"exists": True},
    })
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    calls = {"count": 0}

    def embed_once_then_fail(text):
        calls["count"] += 1
        if calls["count"] <= 2:
            return [0.2] * 1024
        raise embed_mod.EmbedError("ollama down")

    monkeypatch.setattr(embed_mod, "embed", embed_once_then_fail)

    summary = eb.run(["--limit", "8", "--cap-remaining", "8"])

    assert summary["processed"] == 1
    assert summary["failed"] == 1
    assert summary["attempted"] == 2
    assert summary["has_more"] is True
    assert any(
        "embed_attempts = embed_attempts + 1" in c.args[0]
        for c in cur.execute.call_args_list
    )


def test_main_prints_single_line_json(monkeypatch, capsys):
    monkeypatch.setattr(eb, "run", lambda argv: {"processed": 1, "failed": 0, "attempted": 1})

    eb.main(["--limit", "1"])

    out = capsys.readouterr().out.strip()
    assert "\n" not in out
    assert json.loads(out)["processed"] == 1
