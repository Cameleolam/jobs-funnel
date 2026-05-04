"""Smoke tests for scripts/db.py."""
import os
from unittest.mock import patch

import pytest

import scripts.db as db


def test_table_name_defaults_to_jobs(monkeypatch):
    monkeypatch.delenv("JOBS_FUNNEL_TABLE", raising=False)
    assert db.table_name() == "jobs"


def test_table_name_reads_env(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs_test")
    assert db.table_name() == "jobs_test"


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
