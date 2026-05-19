"""Optional database schema detection for the UI."""

import psycopg2

from scripts.db import get_conn
from ui.config import TABLE


# The Phase 1 embedding migration (0003_pgvector.sql) is per-profile-table.
# Human review columns are also optional while Phase 4 migrations roll out.
def _detect_optional_columns():
    wanted = {
        "embedding",
        "scored_uncalibrated",
        "needs_human_review",
        "explanation",
        "confidence",
        "critique_count",
    }
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = ANY(%s)",
                (TABLE, list(wanted)),
            )
            return {r[0] for r in cur.fetchall()}
    except psycopg2.OperationalError:
        return set()
    finally:
        if conn is not None:
            conn.close()


OPTIONAL_COLUMNS = _detect_optional_columns()
HAS_EMBEDDING_COLUMNS = {"embedding", "scored_uncalibrated"}.issubset(OPTIONAL_COLUMNS)
HAS_HUMAN_REVIEW_COLUMNS = {
    "needs_human_review",
    "explanation",
    "confidence",
    "critique_count",
}.issubset(OPTIONAL_COLUMNS)

_BASE_ROW_COLS = (
    "id, url, title, company, location, source, fit_score, decision, "
    "cv_variant, reasoning, status, crawled_at, analyzed_at, "
    "salary_min, salary_max, salary_currency, remote, likely_english, "
    "staffing_agency, geo_mismatch, "
    "tags, priority_notes, notes, user_status, "
    "posted_at, employment_type, seniority_level, start_date, "
    "error, error_code, retry_count, "
    "possible_duplicate_of, duplicate_confirmed, "
    "tracked_at"
)

if HAS_EMBEDDING_COLUMNS:
    ROW_COLS = (
        f"{_BASE_ROW_COLS}, "
        "(embedding IS NULL) AS awaiting_embedding, scored_uncalibrated"
    )
else:
    ROW_COLS = (
        f"{_BASE_ROW_COLS}, "
        "FALSE AS awaiting_embedding, FALSE AS scored_uncalibrated"
    )

if HAS_HUMAN_REVIEW_COLUMNS:
    ROW_COLS = (
        f"{ROW_COLS}, needs_human_review, explanation, confidence, critique_count"
    )
else:
    ROW_COLS = (
        f"{ROW_COLS}, FALSE AS needs_human_review, NULL AS explanation, "
        "NULL AS confidence, 0 AS critique_count"
    )
