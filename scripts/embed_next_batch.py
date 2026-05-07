#!/usr/bin/env python3
"""Embed one bounded batch of jobs and print a single JSON summary line."""
import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2.extras

from scripts import db, embed as embed_mod
from scripts.backfill_embeddings import _record_failure, _write_embeddings


DEFAULT_LIMIT = 8


def _effective_limit(limit: int, cap_remaining: int) -> int:
    if limit < 0:
        raise ValueError("--limit must be >= 0")
    if cap_remaining < 0:
        return limit
    return min(limit, cap_remaining)


def _select_next_batch(cur, table: str, limit: int):
    cur.execute(
        f"SELECT id, title, company, location, description, remote, "
        f"  seniority_level, employment_type, likely_english "
        f"FROM {table} "
        f"WHERE status IN ('pending', 'error') "
        f"  AND retry_count < 3 "
        f"  AND (embedding IS NULL OR embedding_calibration IS NULL) "
        f"  AND error_code IS NULL "
        f"ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END, id "
        f"LIMIT %s",
        (limit,),
    )
    return cur.fetchall()


def _has_more(cur, table: str) -> bool:
    cur.execute(
        f"SELECT EXISTS ("
        f"SELECT 1 FROM {table} "
        f"WHERE status IN ('pending', 'error') "
        f"  AND retry_count < 3 "
        f"  AND (embedding IS NULL OR embedding_calibration IS NULL) "
        f"  AND error_code IS NULL"
        f") AS exists"
    )
    row = cur.fetchone()
    if row is None:
        return False
    if isinstance(row, dict):
        return bool(row.get("exists"))
    return bool(row[0])


def run(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(description="Embed the next bounded batch of missing jobs.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--cap-remaining", type=int, default=-1)
    args = parser.parse_args(argv)

    batch_id = uuid.uuid4().hex
    effective_limit = _effective_limit(args.limit, args.cap_remaining)

    if effective_limit == 0:
        return {
            "batch_id": batch_id,
            "processed": 0,
            "failed": 0,
            "attempted": 0,
            "has_more": True,
            "capped": args.cap_remaining == 0,
            "batch_size": 0,
            "model": embed_mod.MODEL,
        }

    table = db.table_name()
    conn = db.get_vector_conn()
    conn.rollback()
    conn.autocommit = True
    summary = {
        "batch_id": batch_id,
        "processed": 0,
        "failed": 0,
        "attempted": 0,
        "has_more": False,
        "capped": False,
        "batch_size": effective_limit,
        "model": embed_mod.MODEL,
        "table": table,
    }

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _select_next_batch(cur, table, effective_limit)
            for row in rows:
                job = dict(row)
                try:
                    dedup_vec = embed_mod.embed(embed_mod.text_for_dedup(job))
                    calib_vec = embed_mod.embed(embed_mod.text_for_calibration(job))
                except embed_mod.EmbedError:
                    _record_failure(cur, table, job["id"])
                    summary["failed"] += 1
                    summary["attempted"] += 1
                    continue
                _write_embeddings(cur, table, job["id"], dedup_vec, calib_vec, embed_mod.MODEL)
                summary["processed"] += 1
                summary["attempted"] += 1
            summary["has_more"] = _has_more(cur, table)
            summary["capped"] = args.cap_remaining >= 0 and summary["attempted"] >= args.cap_remaining
        return summary
    finally:
        conn.close()


def main(argv=None):
    summary = run(sys.argv[1:] if argv is None else argv)
    print(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
