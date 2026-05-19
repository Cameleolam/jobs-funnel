"""Database helpers for the Jobs Funnel UI."""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from fastapi import HTTPException

from scripts import db as scripts_db


@contextmanager
def get_db():
    try:
        conn = scripts_db.get_conn()
    except psycopg2.OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def fetch_all(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetch_one(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def execute(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
