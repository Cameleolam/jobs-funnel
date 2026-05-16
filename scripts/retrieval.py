#!/usr/bin/env python3
"""Few-shot calibration retrieval for scoring."""
from __future__ import annotations

from typing import Any

import psycopg2.extras

from scripts import calibration_settings
from scripts import db
from scripts import embed as embed_mod


def calibration_k() -> int:
    return calibration_settings.calibration_k()


def calibration_min_pool() -> int:
    return calibration_settings.calibration_min_pool()


def calibration_k_batch() -> int:
    return calibration_settings.calibration_k_batch()


def weights() -> dict[str, float]:
    return calibration_settings.retrieval_weights()


def _short_text(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def format_anchor(anchor: dict[str, Any], index: int) -> str:
    title = str(anchor.get("title") or "Untitled")
    company = str(anchor.get("company") or "Unknown")
    score = anchor.get("fit_score")
    label = str(anchor.get("calibration_label") or anchor.get("user_status") or "unknown")
    outcome = f"Score: {score if score is not None else '?'} -> {label}"
    if anchor.get("reached_interview"):
        outcome += " -> reached interview"
    if anchor.get("received_offer"):
        outcome += " -> received offer"

    note = _short_text(anchor.get("notes"))
    if note:
        rationale = f"Your note: {note}"
    else:
        rationale = f"Your prior reasoning: {_short_text(anchor.get('reasoning'))}"

    return f'{index}. "{title} @ {company}"\n   {outcome}\n   {rationale}'


def format_calibration_block(anchors: list[dict[str, Any]]) -> str:
    if not anchors:
        return ""
    lines = [
        "CALIBRATION - here's how you handled similar jobs in the past.",
        "Use these as calibration anchors, not as hard rules.",
        "",
    ]
    lines.extend(format_anchor(anchor, i) for i, anchor in enumerate(anchors, start=1))
    return "\n\n".join(lines)


def merge_batch_anchors(anchor_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    best_by_id: dict[int, dict[str, Any]] = {}
    for group in anchor_groups:
        for anchor in group:
            try:
                anchor_id = int(anchor["id"])
            except (KeyError, TypeError, ValueError):
                continue
            current = best_by_id.get(anchor_id)
            if current is None or float(anchor.get("weighted_score") or 0) > float(current.get("weighted_score") or 0):
                best_by_id[anchor_id] = dict(anchor)

    ordered = sorted(
        best_by_id.values(),
        key=lambda a: float(a.get("weighted_score") or 0),
        reverse=True,
    )
    return ordered[: calibration_k_batch()]


def retrieve_similar_decisions(new_job: dict[str, Any], k: int | None = None) -> list[dict[str, Any]]:
    limit = calibration_k() if k is None else k
    if limit <= 0:
        return []
    try:
        vec = embed_mod.embed(embed_mod.text_for_calibration(new_job))
    except Exception:
        return []

    conn = None
    try:
        table = db.table_name()
        events_table = db.events_table_name()
        seniority = new_job.get("seniority_level") or "unspecified"
        w = weights()

        conn = db.get_vector_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM {table}
                    WHERE embedding_calibration IS NOT NULL
                      AND user_status IN ('interested','applied','in_process','offer','dismissed','rejected')
                    """
                )
                row = cur.fetchone() or {"n": 0}
                if int(row["n"]) < calibration_min_pool():
                    return []

                cur.execute(
                    f"""
                    WITH candidates AS (
                        SELECT
                            id,
                            title,
                            company,
                            fit_score,
                            decision,
                            reasoning,
                            notes,
                            user_status,
                            seniority_level,
                            CASE WHEN user_status = 'rejected' THEN 'applied'
                                 ELSE user_status END AS calibration_label,
                            EXISTS (
                                SELECT 1 FROM {events_table} e
                                WHERE e.job_id = {table}.id AND e.kind = 'interview'
                            ) AS reached_interview,
                            (
                                user_status = 'offer'
                                OR EXISTS (
                                    SELECT 1 FROM {events_table} e
                                    WHERE e.job_id = {table}.id
                                      AND e.kind = 'decision'
                                      AND LOWER(e.label) LIKE '%%offer%%'
                                )
                            ) AS received_offer,
                            1 - (embedding_calibration <=> %s::vector) AS similarity
                        FROM {table}
                        WHERE embedding_calibration IS NOT NULL
                          AND user_status IN ('interested','applied','in_process','offer','dismissed','rejected')
                    )
                    SELECT *,
                        similarity * (
                            CASE
                                WHEN calibration_label = 'offer' THEN %s
                                WHEN reached_interview OR calibration_label = 'in_process' THEN %s
                                WHEN calibration_label = 'applied' THEN %s
                                WHEN calibration_label = 'dismissed' AND notes IS NOT NULL AND TRIM(notes) <> '' THEN %s
                                WHEN calibration_label = 'dismissed' THEN %s
                                WHEN calibration_label = 'interested' THEN %s
                                ELSE 1.0
                            END
                        ) AS weighted_score
                    FROM candidates
                    ORDER BY
                        (CASE WHEN seniority_level = %s THEN 0 ELSE 1 END),
                        weighted_score DESC
                    LIMIT %s
                    """,
                    (
                        vec,
                        w["offer"],
                        w["interview"],
                        w["applied"],
                        w["dismiss_note"],
                        w["dismiss"],
                        w["interested"],
                        seniority,
                        limit,
                    ),
                )
                return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
