"""Apply the fresh setup baseline and any remaining migrations for the active table."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import run_migration


PROJECT_DIR = Path(__file__).resolve().parent.parent
SETUP_SQL = PROJECT_DIR / "scripts" / "setup_db.sql"
MIGRATIONS_DIR = PROJECT_DIR / "scripts" / "migrations"


def sql_plan(
    *,
    setup_path: Path = SETUP_SQL,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[Path]:
    paths = [setup_path]
    if migrations_dir.is_dir():
        paths.extend(sorted(migrations_dir.glob("*.sql")))
    return paths


def apply_sql_file(cur, path: Path, table: str, *, track: bool) -> str:
    name = path.name
    if track and run_migration.already_applied(cur, name, table):
        return "skipped"

    raw_sql = path.read_text(encoding="utf-8")
    sql = run_migration.resolve_placeholders(raw_sql, table)
    cur.execute(sql)
    if track:
        run_migration.record_applied(cur, name, table)
    return "applied"


def run() -> list[tuple[str, str]]:
    load_dotenv(PROJECT_DIR / ".env")
    table = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")
    paths = sql_plan()
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    conn = run_migration.connect()
    results: list[tuple[str, str]] = []
    try:
        with conn:
            with conn.cursor() as cur:
                run_migration.ensure_tracking_table(cur)
                for path in paths:
                    track = path.name != "setup_db.sql"
                    status = apply_sql_file(cur, path, table, track=track)
                    results.append((path.name, status))
        return results
    finally:
        conn.close()


def main() -> int:
    try:
        results = run()
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    for name, status in results:
        print(f"{status.upper():7} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
