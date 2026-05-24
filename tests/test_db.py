"""Smoke tests for scripts/db.py."""
import os
from unittest.mock import patch, MagicMock

import pytest

import scripts.db as db
from scripts.lib.sql_identifiers import validate_identifier


def test_table_name_defaults_to_jobs(monkeypatch):
    monkeypatch.setattr(db, "_DOTENV_LOADED", True)
    monkeypatch.delenv("JOBS_FUNNEL_TABLE", raising=False)
    assert db.table_name() == "jobs"


def test_table_name_reads_env(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs_test")
    assert db.table_name() == "jobs_test"


def test_table_name_rejects_invalid_identifier(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs; DROP TABLE jobs; --")
    with pytest.raises(ValueError, match="Invalid JOBS_FUNNEL_TABLE"):
        db.table_name()


def test_validate_identifier_accepts_sql_identifier():
    assert validate_identifier("jobs_profile1", "JOBS_FUNNEL_TABLE") == "jobs_profile1"


def test_calibration_table_names_follow_active_jobs_table(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs_profile1")

    assert db.calibration_settings_table_name() == "jobs_profile1_calibration_settings"
    assert db.calibration_proposals_table_name() == "jobs_profile1_calibration_proposals"


def test_get_conn_uses_env_vars(monkeypatch):
    captured = {}

    class FakeConn:
        pass

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConn()

    monkeypatch.setenv("JOBS_FUNNEL_PG_HOST", "h")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PORT", "1234")
    monkeypatch.setenv("JOBS_FUNNEL_PG_DATABASE", "d")
    monkeypatch.setenv("JOBS_FUNNEL_PG_USER", "u")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PASSWORD", "p")

    with patch("psycopg2.connect", side_effect=fake_connect):
        db.get_conn()

    assert captured == {"host": "h", "port": "1234", "dbname": "d", "user": "u", "password": "p"}


def test_get_conn_passes_optional_connect_timeout(monkeypatch):
    captured = {}

    class FakeConn:
        pass

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConn()

    monkeypatch.setenv("JOBS_FUNNEL_PG_HOST", "h")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PORT", "1234")
    monkeypatch.setenv("JOBS_FUNNEL_PG_DATABASE", "d")
    monkeypatch.setenv("JOBS_FUNNEL_PG_USER", "u")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PASSWORD", "p")

    with patch("psycopg2.connect", side_effect=fake_connect):
        db.get_conn(connect_timeout=2)

    assert captured == {
        "host": "h",
        "port": "1234",
        "dbname": "d",
        "user": "u",
        "password": "p",
        "connect_timeout": 2,
    }


def test_register_vector_calls_pgvector(monkeypatch):
    fake_conn = MagicMock()
    with patch("pgvector.psycopg2.register_vector") as reg:
        db.register_vector(fake_conn)
    reg.assert_called_once_with(fake_conn)


def test_get_vector_conn_registers_vector(monkeypatch):
    fake_conn = MagicMock()

    def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setenv("JOBS_FUNNEL_PG_HOST", "h")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PORT", "5432")
    monkeypatch.setenv("JOBS_FUNNEL_PG_DATABASE", "d")
    monkeypatch.setenv("JOBS_FUNNEL_PG_USER", "u")
    monkeypatch.setenv("JOBS_FUNNEL_PG_PASSWORD", "p")

    with patch("psycopg2.connect", side_effect=fake_connect), \
         patch("pgvector.psycopg2.register_vector") as reg:
        out = db.get_vector_conn()

    assert out is fake_conn
    reg.assert_called_once_with(fake_conn)
