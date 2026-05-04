"""Backfill embeddings for jobs that don't have them.

Modes (mutually exclusive):
  default                    Embed rows where embedding IS NULL AND error_code IS NULL.
  --force-retry-dead         Also retry rows previously marked error_code='EMBED_FAILED'.
                             Resets embed_attempts to 0 before retry.
  --rescore-uncalibrated     Flip status='pending' on rows scored_uncalibrated=TRUE
                             whose calibration vector is now populated, so the
                             analyze loop re-scores them with calibration.

Common:
  --limit N                  Cap number of rows processed (default 200).
  --dry-run                  Print what would change; don't write.

Resumable: each successful embed is committed in its own transaction, so a
mid-run kill leaves a consistent partial state.
"""
import argparse
import json
import sys

import psycopg2.extras

from scripts import db, embed as embed_mod


def _select_missing(cur, table: str, force_retry: bool, limit: int):
    if force_retry:
        sql = (
            f"SELECT id, title, company, location, description, remote, "
            f"  seniority_level, employment_type, likely_english "
            f"FROM {table} "
            f"WHERE (embedding IS NULL OR embedding_calibration IS NULL) "
            f"  AND (error_code = 'EMBED_FAILED' OR error_code IS NULL) "
            f"ORDER BY id LIMIT %s"
        )
    else:
        sql = (
            f"SELECT id, title, company, location, description, remote, "
            f"  seniority_level, employment_type, likely_english "
            f"FROM {table} "
            f"WHERE (embedding IS NULL OR embedding_calibration IS NULL) "
            f"  AND error_code IS NULL "
            f"ORDER BY id LIMIT %s"
        )
    cur.execute(sql, (limit,))
    return cur.fetchall()


def _select_rescore_targets(cur, table: str, limit: int):
    cur.execute(
        f"SELECT id FROM {table} "
        f"WHERE scored_uncalibrated = TRUE "
        f"  AND embedding_calibration IS NOT NULL "
        f"ORDER BY id LIMIT %s",
        (limit,),
    )
    return cur.fetchall()


def _write_embeddings(cur, table, job_id, dedup_vec, calib_vec, model):
    cur.execute(
        f"UPDATE {table} SET "
        f"  embedding = %s, "
        f"  embedding_calibration = %s, "
        f"  embedded_at = NOW(), "
        f"  embed_model = %s, "
        f"  embed_attempts = 0, "
        f"  error_code = CASE WHEN error_code = 'EMBED_FAILED' THEN NULL ELSE error_code END "
        f"WHERE id = %s",
        (dedup_vec, calib_vec, model, job_id),
    )


def _record_failure(cur, table, job_id):
    cur.execute(
        f"UPDATE {table} SET "
        f"  embed_attempts = embed_attempts + 1, "
        f"  error_code = CASE WHEN embed_attempts + 1 >= 3 THEN 'EMBED_FAILED' ELSE error_code END "
        f"WHERE id = %s",
        (job_id,),
    )


def _requeue_for_rescore(cur, table, job_id):
    cur.execute(
        f"UPDATE {table} SET "
        f"  status = 'pending', "
        f"  scored_uncalibrated = FALSE "
        f"WHERE id = %s",
        (job_id,),
    )


def run(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(description="Backfill embeddings.")
    parser.add_argument("--force-retry-dead", action="store_true")
    parser.add_argument("--rescore-uncalibrated", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    table = db.table_name()
    conn = db.get_vector_conn()
    summary = {"processed": 0, "failed": 0, "requeued": 0, "table": table}
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if args.rescore_uncalibrated:
                    rows = _select_rescore_targets(cur, table, args.limit)
                    for r in rows:
                        if args.dry_run:
                            summary["requeued"] += 1
                            continue
                        _requeue_for_rescore(cur, table, r["id"])
                        summary["requeued"] += 1
                    return summary

                rows = _select_missing(cur, table, args.force_retry_dead, args.limit)
                for r in rows:
                    if args.dry_run:
                        summary["processed"] += 1
                        continue
                    try:
                        dedup_vec = embed_mod.embed(embed_mod.text_for_dedup(dict(r)))
                        calib_vec = embed_mod.embed(embed_mod.text_for_calibration(dict(r)))
                    except embed_mod.EmbedError:
                        _record_failure(cur, table, r["id"])
                        summary["failed"] += 1
                        continue
                    _write_embeddings(cur, table, r["id"], dedup_vec, calib_vec, embed_mod.MODEL)
                    summary["processed"] += 1
        return summary
    finally:
        conn.close()


def main():
    summary = run(sys.argv[1:])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
