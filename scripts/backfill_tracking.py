"""One-time backfill: for every job with applied_at set, create one
synthetic 'application' event and mark the job as tracked.

Idempotent: skips jobs that already have any job_events row.
Run manually:
    python scripts/backfill_tracking.py
"""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

try:
    from scripts.lib.sql_identifiers import validate_identifier
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.lib.sql_identifiers import validate_identifier


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    table = validate_identifier(os.environ.get("JOBS_FUNNEL_TABLE", "jobs"), "JOBS_FUNNEL_TABLE")
    events_table = f"{table}_events"
    conn = psycopg2.connect(
        host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    )
    with conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT j.id, j.applied_at "
            f"FROM {table} j "
            f"LEFT JOIN {events_table} e ON e.job_id = j.id "
            f"WHERE j.applied_at IS NOT NULL AND e.id IS NULL "
            f"GROUP BY j.id, j.applied_at"
        )
        rows = cur.fetchall()
        for job_id, applied_at in rows:
            cur.execute(
                f"INSERT INTO {events_table} (job_id, occurred_at, kind, label) "
                f"VALUES (%s, %s, 'application', 'Applied')",
                (job_id, applied_at),
            )
            cur.execute(
                f"UPDATE {table} SET tracked_at = COALESCE(tracked_at, %s) "
                f"WHERE id = %s",
                (applied_at, job_id),
            )
        print(f"Backfilled {len(rows)} job(s)")
    conn.close()


if __name__ == "__main__":
    main()
