#!/usr/bin/env python3
"""Tiered semantic dedup using pgvector first and Claude only for borderline pairs."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

import psycopg2.extras

from scripts import db


THRESHOLD_CERTAIN = float(os.environ.get("DEDUP_THRESHOLD_CERTAIN", "0.95"))
THRESHOLD_REVIEW = float(os.environ.get("DEDUP_THRESHOLD_REVIEW", "0.85"))
SCOPE_DAYS = int(os.environ.get("DEDUP_SCOPE_DAYS", "30"))

CLAUDE_PROMPT = """\
You are deciding whether two job postings are the same role.

Return one compact JSON object only:
{{"duplicate": true|false, "reason": "short reason"}}

Rules:
- Same company or recruiter-for-company, very similar role, and same city can be duplicate.
- Different role families are not duplicates.
- Different locations are not duplicates.
- When uncertain, return duplicate=false.

NEW JOB:
{new_job}

CANDIDATE:
{candidate}
"""


@dataclass(frozen=True)
class DedupDecision:
    new_id: int
    existing_id: int | None
    decision_path: str
    similarity: float | None = None
    confidence: str = "none"
    reason: str = ""

    def to_pair(self) -> dict[str, Any] | None:
        if self.existing_id is None:
            return None
        return {
            "new_id": self.new_id,
            "existing_id": self.existing_id,
            "confidence": self.confidence,
            "reason": self.reason[:200],
            "decision_path": self.decision_path,
            "similarity": self.similarity,
        }


def classify_similarity(similarity: float | None) -> str:
    if similarity is None:
        return "no_match"
    if similarity >= THRESHOLD_CERTAIN:
        return "vector_certain"
    if similarity < THRESHOLD_REVIEW:
        return "vector_clear"
    return "claude_review"


def _load_job(cur, table: str, job_id: int) -> dict[str, Any] | None:
    cur.execute(
        f"""
        SELECT id, title, company, location, embedding
        FROM {table}
        WHERE id = %s
        """,
        (job_id,),
    )
    return cur.fetchone()


def _nearest_vector_match(
    cur,
    table: str,
    job: dict[str, Any],
    scope_days: int,
) -> dict[str, Any] | None:
    cur.execute(
        f"""
        SELECT
            id,
            title,
            company,
            location,
            1 - (embedding <=> %s) AS similarity
        FROM {table}
        WHERE id <> %s
          AND embedding IS NOT NULL
          AND status = 'analyzed'
          AND crawled_at > NOW() - make_interval(days => %s)
        ORDER BY embedding <=> %s
        LIMIT 1
        """,
        (job["embedding"], job["id"], scope_days, job["embedding"]),
    )
    return cur.fetchone()


def _parse_claude_json(stdout: str) -> dict[str, Any] | None:
    try:
        outer = json.loads(stdout)
        payload = outer.get("result", outer) if isinstance(outer, dict) else outer
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload if isinstance(payload, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _claude_review_decision(job: dict[str, Any], match: dict[str, Any], similarity: float) -> DedupDecision:
    prompt = CLAUDE_PROMPT.format(
        new_job=json.dumps({k: job.get(k) for k in ("id", "title", "company", "location")}, ensure_ascii=False),
        candidate=json.dumps({k: match.get(k) for k in ("id", "title", "company", "location")}, ensure_ascii=False),
    )
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return DedupDecision(int(job["id"]), None, "claude_error", similarity)

    if result.returncode != 0:
        return DedupDecision(int(job["id"]), None, "claude_error", similarity)

    parsed = _parse_claude_json(result.stdout)
    if not parsed:
        return DedupDecision(int(job["id"]), None, "claude_error", similarity)

    reason = str(parsed.get("reason") or "")[:200]
    if parsed.get("duplicate") is True:
        return DedupDecision(int(job["id"]), int(match["id"]), "claude_dup", similarity, "medium", reason)
    return DedupDecision(int(job["id"]), None, "claude_clear", similarity, "none", reason)


def find_duplicate_by_id(
    job_id: int,
    table: str | None = None,
    scope_days: int = SCOPE_DAYS,
) -> DedupDecision:
    table = table or db.table_name()
    conn = db.get_vector_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                job = _load_job(cur, table, job_id)
                if job is None:
                    return DedupDecision(job_id, None, "missing_job")
                if job.get("embedding") is None:
                    return DedupDecision(int(job["id"]), None, "no_embedding")

                match = _nearest_vector_match(cur, table, job, scope_days)
                if match is None:
                    return DedupDecision(int(job["id"]), None, "no_match")

                similarity = match.get("similarity")
                decision_path = classify_similarity(similarity)
                if decision_path == "vector_certain":
                    return DedupDecision(
                        int(job["id"]),
                        int(match["id"]),
                        "vector_certain",
                        similarity,
                        "high",
                        "Vector similarity exceeded duplicate threshold",
                    )
                if decision_path == "vector_clear":
                    return DedupDecision(int(job["id"]), None, "vector_clear", similarity)
                return _claude_review_decision(job, match, similarity)
    finally:
        conn.close()
