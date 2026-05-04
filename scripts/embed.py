"""Local embedding via Ollama + bge-m3.

Returns 1024-dim vectors by default. Multilingual (DE+EN).

Two text builders:
  text_for_dedup       — title-heavy text (title repeated to weight it)
  text_for_calibration — structured prefix (TITLE/COMPANY/...) + description
"""
import os

import httpx


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/embeddings"
MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3")
DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
TIMEOUT = 30.0
DESC_MAX_CHARS = 3000


class EmbedError(Exception):
    """Raised when the Ollama embedding call fails or returns the wrong shape."""


def embed(text: str) -> list[float]:
    """Return a list[float] embedding from Ollama.

    Raises EmbedError on HTTP failure, missing field, or dim mismatch.
    """
    try:
        r = httpx.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": text},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()
        vec = payload["embedding"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        raise EmbedError(f"Ollama call failed: {e}") from e

    if not isinstance(vec, list) or len(vec) != DIM:
        raise EmbedError(f"Expected {DIM} dims, got {len(vec) if isinstance(vec, list) else type(vec).__name__}")
    return vec


def text_for_dedup(job: dict) -> str:
    """Title-heavy text for the dedup vector. Title repeated to weight it."""
    title = (job.get("title") or "")
    company = (job.get("company") or "")
    description = (job.get("description") or "")[:DESC_MAX_CHARS]
    return f"{title}\n{title}\n{company}\n{description}"


def text_for_calibration(job: dict) -> str:
    """Structured-prefix text for calibration retrieval.

    The structured fields make the embedding sensitive to seniority / employment
    type / language without those signals being drowned out by the description.
    """
    fields = {
        "TITLE":      job.get("title") or "",
        "COMPANY":    job.get("company") or "",
        "LOCATION":   job.get("location") or "",
        "REMOTE":     "yes" if job.get("remote") else "no",
        "SENIORITY":  job.get("seniority_level") or "unspecified",
        "EMPLOYMENT": job.get("employment_type") or "unspecified",
        "LANGUAGE":   "english" if job.get("likely_english") else "german",
    }
    header = "\n".join(f"{k}: {v}" for k, v in fields.items())
    description = (job.get("description") or "")[:DESC_MAX_CHARS]
    return f"{header}\n---\n{description}"


import argparse
import json
import sys
from pathlib import Path

# Allow direct invocation: `python scripts/embed.py --job-id N`.
# When run as a module (`python -m scripts.embed`) this is a no-op.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2.extras

from scripts import db


SELECT_COLS = (
    "id, title, company, location, description, remote, "
    "seniority_level, employment_type, likely_english"
)


def _select_job(cur, table: str, job_id: int):
    cur.execute(
        f"SELECT {SELECT_COLS} FROM {table} WHERE id = %s",
        (job_id,),
    )
    return cur.fetchone()


def _write_embeddings(cur, table: str, job_id: int, dedup_vec, calib_vec, model: str):
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


def _record_failure(cur, table: str, job_id: int):
    """Increment embed_attempts; mark EMBED_FAILED at >=3."""
    cur.execute(
        f"UPDATE {table} SET "
        f"  embed_attempts = embed_attempts + 1, "
        f"  error_code = CASE WHEN embed_attempts + 1 >= 3 THEN 'EMBED_FAILED' ELSE error_code END "
        f"WHERE id = %s",
        (job_id,),
    )


def run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Embed a single job by id.")
    parser.add_argument("--job-id", type=int, required=True)
    args = parser.parse_args(argv)

    table = db.table_name()
    conn = db.get_vector_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _select_job(cur, table, args.job_id)
                if row is None:
                    print(json.dumps({
                        "job_id": args.job_id,
                        "status": "error",
                        "error": f"Job {args.job_id} not found in {table}",
                    }))
                    return 1
                try:
                    dedup_vec = embed(text_for_dedup(dict(row)))
                    calib_vec = embed(text_for_calibration(dict(row)))
                except EmbedError as e:
                    _record_failure(cur, table, args.job_id)
                    print(json.dumps({
                        "job_id": args.job_id,
                        "status": "embed_failed",
                        "error": str(e),
                    }))
                    return 2
                _write_embeddings(cur, table, args.job_id, dedup_vec, calib_vec, MODEL)
                print(json.dumps({
                    "job_id": args.job_id,
                    "status": "ok",
                    "dim": len(dedup_vec),
                    "model": MODEL,
                }))
                return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
