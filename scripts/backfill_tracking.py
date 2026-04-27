"""One-time backfill: for every job with applied_at set, create one
synthetic 'application' event and mark the job as tracked.

Idempotent: skips jobs that already have any job_events row.
Run manually:
    python scripts/backfill_tracking.py
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    table = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")
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
            f"LEFT JOIN job_events e ON e.job_id = j.id "
            f"WHERE j.applied_at IS NOT NULL AND e.id IS NULL "
            f"GROUP BY j.id, j.applied_at"
        )
        rows = cur.fetchall()
        for job_id, applied_at in rows:
            cur.execute(
                "INSERT INTO job_events (job_id, occurred_at, kind, label) "
                "VALUES (%s, %s, 'application', 'Applied')",
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
