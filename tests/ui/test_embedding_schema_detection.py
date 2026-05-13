"""Phase 1 stabilization: UI must tolerate DBs with optional columns.

We exercise the detection function directly (mocking psycopg2.connect) and use
module reloads only for import-time ROW_COLS checks.
"""
import importlib
from unittest.mock import MagicMock, patch

import ui.server as srv


def _fake_conn(present_cols):
    cursor = MagicMock()
    cursor.fetchall.return_value = [(c,) for c in present_cols]
    cursor.__enter__ = lambda self: self
    cursor.__exit__ = lambda *a: None

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.close = MagicMock()
    return conn


def test_detect_returns_optional_columns_when_present():
    with patch("psycopg2.connect", return_value=_fake_conn(["embedding", "scored_uncalibrated"])):
        assert srv._detect_optional_columns() == {"embedding", "scored_uncalibrated"}


def test_detect_returns_empty_set_when_columns_missing():
    with patch("psycopg2.connect", return_value=_fake_conn([])):
        assert srv._detect_optional_columns() == set()


def test_has_embedding_columns_stays_false_when_only_one_column_present(monkeypatch):
    # Defensive: a half-applied migration shouldn't enable the embedding code path.
    monkeypatch.setattr("psycopg2.connect", lambda **kwargs: _fake_conn(["embedding"]))
    importlib.reload(srv)

    assert srv.HAS_EMBEDDING_COLUMNS is False


def test_detect_returns_empty_set_when_db_unreachable():
    import psycopg2
    with patch("psycopg2.connect", side_effect=psycopg2.OperationalError("nope")):
        assert srv._detect_optional_columns() == set()


def test_row_cols_at_module_load_matches_detection_flag():
    # Whatever the live DB reports, ROW_COLS must agree with HAS_EMBEDDING_COLUMNS.
    if srv.HAS_EMBEDDING_COLUMNS:
        assert "(embedding IS NULL) AS awaiting_embedding" in srv.ROW_COLS
        assert ", scored_uncalibrated" in srv.ROW_COLS
    else:
        assert "FALSE AS awaiting_embedding" in srv.ROW_COLS
        assert "FALSE AS scored_uncalibrated" in srv.ROW_COLS
        assert "embedding IS NULL" not in srv.ROW_COLS

    if srv.HAS_HUMAN_REVIEW_COLUMNS:
        assert "needs_human_review" in srv.ROW_COLS
        assert "explanation" in srv.ROW_COLS
        assert "confidence" in srv.ROW_COLS
        assert "critique_count" in srv.ROW_COLS
    else:
        assert "FALSE AS needs_human_review" in srv.ROW_COLS
        assert "NULL AS explanation" in srv.ROW_COLS
        assert "NULL AS confidence" in srv.ROW_COLS
        assert "0 AS critique_count" in srv.ROW_COLS


def test_row_cols_include_human_review_when_columns_exist(monkeypatch):
    monkeypatch.setattr(
        "psycopg2.connect",
        lambda **kwargs: _fake_conn([
            "embedding",
            "scored_uncalibrated",
            "needs_human_review",
            "explanation",
            "confidence",
            "critique_count",
        ]),
    )
    importlib.reload(srv)

    assert "needs_human_review" in srv.ROW_COLS
    assert "explanation" in srv.ROW_COLS
    assert "confidence" in srv.ROW_COLS
    assert "critique_count" in srv.ROW_COLS
    assert "FALSE AS needs_human_review" not in srv.ROW_COLS


def test_row_cols_alias_human_review_when_columns_missing(monkeypatch):
    monkeypatch.setattr("psycopg2.connect", lambda **kwargs: _fake_conn([]))
    importlib.reload(srv)

    assert "FALSE AS needs_human_review" in srv.ROW_COLS
    assert "NULL AS explanation" in srv.ROW_COLS
    assert "NULL AS confidence" in srv.ROW_COLS
    assert "0 AS critique_count" in srv.ROW_COLS


def test_review_filter_uses_human_review_columns_when_available(monkeypatch):
    monkeypatch.setattr(srv, "HAS_HUMAN_REVIEW_COLUMNS", True)

    where, params = srv.build_job_filter(view="review")

    assert where == (
        "status = 'analyzed' AND "
        "(needs_human_review = TRUE OR decision = 'pending_review')"
    )
    assert params == []


def test_review_filter_falls_back_to_pending_review_decision(monkeypatch):
    monkeypatch.setattr(srv, "HAS_HUMAN_REVIEW_COLUMNS", False)

    where, params = srv.build_job_filter(view="review")

    assert where == "status = 'analyzed' AND decision = 'pending_review'"
    assert params == []
