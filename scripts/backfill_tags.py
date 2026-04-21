"""One-shot backfill: recompute staffing_agency / geo_mismatch / likely_english
against the active country pack and update rows whose values have drifted.

Usage:
    python scripts/backfill_tags.py            # live mode, writes to DB
    python scripts/backfill_tags.py --dry-run  # compute diffs, no writes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.lib.country_pack import load_pack
from scripts.lib.soft_tags import (
    detect_geo_mismatch,
    detect_staffing_agency,
    is_likely_english,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Compute diffs but skip writes")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    profile = os.environ.get("JOBS_FUNNEL_PROFILE")
    if not profile:
        print("ERROR: JOBS_FUNNEL_PROFILE env var required", file=sys.stderr)
        return 2

    search_path = ROOT / "profiles" / profile / "search.json"
    if not search_path.is_file():
        print(f"ERROR: profile search.json not found at {search_path}", file=sys.stderr)
        return 2
    search = json.loads(search_path.read_text(encoding="utf-8"))
    country_code = search.get("country", "de")

    pack = load_pack(country_code)
    print(f"Loaded country pack: {pack.name} ({pack.code})")
    print(f"  staffing patterns: {len(pack.staffing_patterns)}")
    print(f"  geo allowlist:     {len(pack.geo_allowlist)}")

    db_conf = dict(
        host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    )
    table = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")

    conn = psycopg2.connect(**db_conf)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                f"SELECT id, company, location, remote, description, "
                f"staffing_agency, geo_mismatch, likely_english FROM {table}"
            )
            rows = cur.fetchall()

        updates = []
        staffing_true_before = staffing_true_after = 0
        geo_true_before = geo_true_after = 0
        en_true_before = en_true_after = 0

        for row in rows:
            new_staffing = detect_staffing_agency(row["company"] or "", pack)
            new_geo = detect_geo_mismatch(row["location"] or "", bool(row["remote"]), pack)
            new_en = is_likely_english(row["description"] or "", pack)

            if row["staffing_agency"]: staffing_true_before += 1
            if row["geo_mismatch"]: geo_true_before += 1
            if row["likely_english"]: en_true_before += 1
            if new_staffing: staffing_true_after += 1
            if new_geo: geo_true_after += 1
            if new_en: en_true_after += 1

            if (
                bool(row["staffing_agency"]) != new_staffing
                or bool(row["geo_mismatch"]) != new_geo
                or bool(row["likely_english"]) != new_en
            ):
                updates.append((new_staffing, new_geo, new_en, row["id"]))

        print(f"Scanned {len(rows)} rows.")
        print(f"  staffing: {staffing_true_before} -> {staffing_true_after}")
        print(f"  geo:      {geo_true_before} -> {geo_true_after}")
        print(f"  english:  {en_true_before} -> {en_true_after}")
        print(f"  rows needing update: {len(updates)}")

        if args.dry_run:
            print("Dry run: no writes.")
            return 0

        if not updates:
            print("Nothing to update.")
            return 0

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                f"UPDATE {table} SET staffing_agency=%s, geo_mismatch=%s, likely_english=%s WHERE id=%s",
                updates,
                page_size=500,
            )
        conn.commit()
        print(f"Updated {len(updates)} rows.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
