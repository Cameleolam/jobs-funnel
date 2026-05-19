from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException

import ui.db as ui_db


def test_get_db_uses_shared_scripts_connection(monkeypatch):
    conn = MagicMock()
    get_conn = Mock(return_value=conn)
    monkeypatch.setattr(ui_db.scripts_db, "get_conn", get_conn)

    with ui_db.get_db() as yielded_conn:
        assert yielded_conn is conn

    get_conn.assert_called_once_with()
    conn.commit.assert_called_once_with()
    conn.close.assert_called_once_with()


def test_get_db_maps_operational_error_to_http_503(monkeypatch):
    monkeypatch.setattr(
        ui_db.scripts_db,
        "get_conn",
        Mock(side_effect=ui_db.psycopg2.OperationalError),
    )

    with pytest.raises(HTTPException) as exc_info:
        with ui_db.get_db():
            pass

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Database unavailable"


def test_fetch_one_uses_real_dict_cursor(monkeypatch):
    row = {"one": 1}
    cur = Mock()
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    @contextmanager
    def fake_get_db():
        yield conn

    monkeypatch.setattr(ui_db, "get_db", fake_get_db)

    result = ui_db.fetch_one("SELECT 1", ("x",))

    assert result == row
    assert conn.cursor.call_args.kwargs["cursor_factory"] is ui_db.psycopg2.extras.RealDictCursor
    cur.execute.assert_called_once_with("SELECT 1", ("x",))
