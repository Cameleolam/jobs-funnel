"""Apply a SQL migration file against the configured Postgres database.

Usage:
    python scripts/run_migration.py scripts/migrations/0001_job_events.sql
"""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_migration.py <path_to_sql_file>", file=sys.stderr)
        sys.exit(2)

    sql_path = Path(sys.argv[1])
    if not sql_path.is_file():
        print(f"Not a file: {sql_path}", file=sys.stderr)
        sys.exit(2)

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    conn = psycopg2.connect(
        host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    )
    sql = sql_path.read_text(encoding="utf-8")
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    conn.close()
    print(f"Applied {sql_path.name}")


if __name__ == "__main__":
    main()
