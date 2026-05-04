"""Apply a SQL migration file against the configured Postgres database.

Migration files may use placeholders that are resolved from environment:
  {{TABLE}}        -> $JOBS_FUNNEL_TABLE (default: jobs)
  {{EVENTS_TABLE}} -> ${JOBS_FUNNEL_TABLE}_events

Index names should be templated too so multiple profiles can coexist in the
same database without colliding (e.g. idx_{{TABLE}}_status).

Usage:
    python scripts/run_migration.py scripts/migrations/0001_job_events.sql
    python scripts/run_migration.py --list           # show applied migrations
"""
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    table_scope TEXT NOT NULL
);
"""


def resolve_placeholders(sql: str, table: str) -> str:
    events_table = f"{table}_events"
    sql = sql.replace("{{TABLE}}", table)
    sql = sql.replace("{{EVENTS_TABLE}}", events_table)
    return sql


def connect():
    return psycopg2.connect(
        host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    )


def ensure_tracking_table(cur):
    cur.execute(SCHEMA_MIGRATIONS_DDL)


def already_applied(cur, name: str, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM schema_migrations WHERE name = %s AND table_scope = %s",
        (name, table),
    )
    return cur.fetchone() is not None


def record_applied(cur, name: str, table: str):
    cur.execute(
        "INSERT INTO schema_migrations (name, table_scope) VALUES (%s, %s) "
        "ON CONFLICT (name) DO NOTHING",
        (name, table),
    )


def list_applied():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    conn = connect()
    with conn:
        with conn.cursor() as cur:
            ensure_tracking_table(cur)
            cur.execute(
                "SELECT name, table_scope, applied_at FROM schema_migrations "
                "ORDER BY applied_at"
            )
            rows = cur.fetchall()
    conn.close()
    if not rows:
        print("(no migrations recorded)")
        return
    for name, scope, applied_at in rows:
        print(f"{applied_at.isoformat()}  {scope:<20}  {name}")


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/run_migration.py <path_to_sql_file>\n"
            "       python scripts/run_migration.py --list",
            file=sys.stderr,
        )
        sys.exit(2)

    if sys.argv[1] == "--list":
        list_applied()
        return

    sql_path = Path(sys.argv[1])
    if not sql_path.is_file():
        print(f"Not a file: {sql_path}", file=sys.stderr)
        sys.exit(2)

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    table = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")

    raw_sql = sql_path.read_text(encoding="utf-8")
    sql = resolve_placeholders(raw_sql, table)

    conn = connect()
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_tracking_table(cur)
                if already_applied(cur, sql_path.name, table):
                    print(f"Skipping {sql_path.name} (already applied to {table})")
                    return
                cur.execute(sql)
                record_applied(cur, sql_path.name, table)
        print(f"Applied {sql_path.name} to {table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
