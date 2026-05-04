"""Phase 1 stabilization: UI must tolerate DBs that haven't run 0003_pgvector.sql.

We exercise the detection function directly (mocking psycopg2.connect) and
separately verify the ROW_COLS branching logic by replicating the conditional.
We avoid `importlib.reload(ui.server)` because it rebinds module attributes
and breaks other tests that patch them.
"""
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


def test_detect_returns_true_when_both_columns_present():
    with patch("psycopg2.connect", return_value=_fake_conn(["embedding", "scored_uncalibrated"])):
        assert srv._detect_embedding_schema() is True


def test_detect_returns_false_when_columns_missing():
    with patch("psycopg2.connect", return_value=_fake_conn([])):
        assert srv._detect_embedding_schema() is False


def test_detect_returns_false_when_only_one_column_present():
    # Defensive: a half-applied migration shouldn't enable the embedding code path.
    with patch("psycopg2.connect", return_value=_fake_conn(["embedding"])):
        assert srv._detect_embedding_schema() is False


def test_detect_returns_false_when_db_unreachable():
    import psycopg2
    with patch("psycopg2.connect", side_effect=psycopg2.OperationalError("nope")):
        assert srv._detect_embedding_schema() is False


def test_row_cols_at_module_load_matches_detection_flag():
    # Whatever the live DB reports, ROW_COLS must agree with HAS_EMBEDDING_COLUMNS.
    if srv.HAS_EMBEDDING_COLUMNS:
        assert "(embedding IS NULL) AS awaiting_embedding" in srv.ROW_COLS
        assert ", scored_uncalibrated" in srv.ROW_COLS
    else:
        assert "FALSE AS awaiting_embedding" in srv.ROW_COLS
        assert "FALSE AS scored_uncalibrated" in srv.ROW_COLS
        assert "embedding IS NULL" not in srv.ROW_COLS
