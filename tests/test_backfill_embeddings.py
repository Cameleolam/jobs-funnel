"""Tests for scripts/backfill_embeddings.py.

We don't spin up a real DB. We mock the cursor and assert which queries fire
under each mode.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import scripts.backfill_embeddings as bf


def _fake_conn(rows_by_query=None):
    """Build a MagicMock conn whose cursor.fetchall returns rows
    from the lookup based on substring match in the executed query."""
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

    cur.execute.side_effect = execute
    cur.fetchall.side_effect = fetchall
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_default_mode_processes_missing_only(monkeypatch):
    rows = [{"id": 1, "title": "T", "company": "C", "description": "d",
             "remote": False, "seniority_level": "mid",
             "employment_type": None, "likely_english": False}]
    conn, cur = _fake_conn({"embedding IS NULL": rows})

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)
    monkeypatch.setattr("scripts.embed.embed", lambda txt: [0.1] * 1024)

    summary = bf.run(["--limit", "10"])
    assert summary["processed"] == 1
    assert summary["failed"] == 0
    # an UPDATE that writes embeddings should have run
    assert any("UPDATE" in c.args[0] and "embedding" in c.args[0]
               for c in cur.execute.call_args_list)


def test_force_retry_dead_resets_attempts(monkeypatch):
    rows = [{"id": 5, "title": "T", "company": "C", "description": "d",
             "remote": False, "seniority_level": None,
             "employment_type": None, "likely_english": False}]
    conn, cur = _fake_conn({"error_code = 'EMBED_FAILED'": rows})

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)
    monkeypatch.setattr("scripts.embed.embed", lambda txt: [0.1] * 1024)

    summary = bf.run(["--force-retry-dead"])
    assert summary["processed"] == 1


def test_rescore_uncalibrated_requeues(monkeypatch):
    rows = [{"id": 7}]
    conn, cur = _fake_conn({"scored_uncalibrated = TRUE": rows})

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    summary = bf.run(["--rescore-uncalibrated"])
    assert summary["requeued"] == 1
    # confirm the UPDATE flips status to pending
    assert any("status = 'pending'" in c.args[0]
               for c in cur.execute.call_args_list)
    # and clears scored_uncalibrated
    assert any("scored_uncalibrated = FALSE" in c.args[0]
               for c in cur.execute.call_args_list)


def test_default_mode_records_failure_on_embed_error(monkeypatch):
    from scripts.embed import EmbedError
    rows = [{"id": 11, "title": "T", "company": "C", "description": "d",
             "remote": False, "seniority_level": None,
             "employment_type": None, "likely_english": False}]
    conn, cur = _fake_conn({"embedding IS NULL": rows})

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: conn)

    def boom(_):
        raise EmbedError("nope")
    monkeypatch.setattr("scripts.embed.embed", boom)

    summary = bf.run(["--limit", "10"])
    assert summary["processed"] == 0
    assert summary["failed"] == 1
    # increment embed_attempts ran
    assert any("embed_attempts = embed_attempts + 1" in c.args[0]
               for c in cur.execute.call_args_list)
