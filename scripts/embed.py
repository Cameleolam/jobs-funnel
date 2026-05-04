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
