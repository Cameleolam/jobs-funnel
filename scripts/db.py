"""Shared psycopg2 connection helper.

All Phase 1+ Python scripts use this so connection settings live in one place.
Mirrors the env-var contract already used by scripts/run_migration.py and
ui/server.py.
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_DOTENV_LOADED = False


def _load_env():
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    _DOTENV_LOADED = True


def table_name() -> str:
    """Active jobs table name. Defaults to 'jobs'."""
    _load_env()
    return os.environ.get("JOBS_FUNNEL_TABLE", "jobs")


def events_table_name() -> str:
    """Active job_events table. Derived as `<TABLE>_events`."""
    return f"{table_name()}_events"


def calibration_settings_table_name() -> str:
    """Active calibration settings table for the current profile table."""
    return f"{table_name()}_calibration_settings"


def calibration_proposals_table_name() -> str:
    """Calibration proposal history table for the current profile table."""
    return f"{table_name()}_calibration_proposals"


def get_conn(connect_timeout: int | None = None):
    """Open a psycopg2 connection from JOBS_FUNNEL_PG_* env vars.

    Caller owns the connection (use `with get_conn() as conn: ...`).
    """
    _load_env()
    kwargs = {
        "host": os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        "port": os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        "dbname": os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        "user": os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        "password": os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    }
    if connect_timeout is not None:
        kwargs["connect_timeout"] = connect_timeout
    return psycopg2.connect(**kwargs)


def register_vector(conn) -> None:
    """Register pgvector type adapters on a psycopg2 connection.

    Idempotent — pgvector handles repeat registration. Call once per new conn.
    """
    from pgvector.psycopg2 import register_vector as _reg
    _reg(conn)


def get_vector_conn():
    """get_conn() + pgvector adapter registration. Use this when binding vectors."""
    conn = get_conn()
    register_vector(conn)
    return conn
