"""Persistence and lifecycle operations for calibration proposals."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

import psycopg2.extras

from scripts import calibration_analytics as analytics
from scripts import calibration_settings as settings
from scripts import db


class ProposalStateError(ValueError):
    """Raised when a proposal cannot move to the requested state."""


_INT_SETTING_KEYS = (
    "review_low",
    "review_high",
    "calibration_k",
    "calibration_k_batch",
    "calibration_min_pool",
)
_WEIGHT_SETTING_KEYS = (
    "weight_offer",
    "weight_interview",
    "weight_applied",
    "weight_dismiss_note",
    "weight_dismiss",
    "weight_interested",
)
_SETTING_KEYS = (*_INT_SETTING_KEYS, *_WEIGHT_SETTING_KEYS)
MAX_WINDOW_DAYS = 365


def fetch_analytics_rows(conn, window_days: int) -> list[dict]:
    """Fetch recent scored jobs with event-derived outcome/review flags."""
    window = _window_days(window_days)
    jobs_table = db.table_name()
    events_table = db.events_table_name()

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT
                j.id,
                j.title,
                j.company,
                j.fit_score,
                j.decision,
                j.user_status,
                j.scoring_provider,
                j.scoring_model,
                j.review_provider,
                j.review_model,
                j.notes,
                EXISTS (
                    SELECT 1
                    FROM {events_table} application_events
                    WHERE application_events.job_id = j.id
                      AND application_events.kind = 'application'
                ) AS has_application,
                EXISTS (
                    SELECT 1
                    FROM {events_table} interview_events
                    WHERE interview_events.job_id = j.id
                      AND interview_events.kind = 'interview'
                ) AS has_interview,
                EXISTS (
                    SELECT 1
                    FROM {events_table} offer_events
                    WHERE offer_events.job_id = j.id
                      AND offer_events.kind = 'decision'
                      AND offer_events.label ILIKE '%%offer%%'
                ) AS has_offer_event,
                EXISTS (
                    SELECT 1
                    FROM {events_table} review_events
                    WHERE review_events.job_id = j.id
                      AND review_events.kind = 'decision'
                      AND review_events.label ILIKE 'Reviewed:%%'
                ) AS has_review_decision,
                latest_review.label AS review_label
            FROM {jobs_table} j
            LEFT JOIN LATERAL (
                SELECT review_events.label
                FROM {events_table} review_events
                WHERE review_events.job_id = j.id
                  AND review_events.kind = 'decision'
                  AND review_events.label ILIKE 'Reviewed:%%'
                ORDER BY review_events.occurred_at DESC, review_events.id DESC
                LIMIT 1
            ) latest_review ON TRUE
            WHERE COALESCE(j.analyzed_at, j.crawled_at) >= NOW() - (%s * INTERVAL '1 day')
              AND j.status = 'analyzed'
            ORDER BY COALESCE(j.analyzed_at, j.crawled_at) DESC, j.id DESC
            """,
            (window,),
        )
        return [dict(row) for row in cur.fetchall()]


def generate_proposal(window_days: int = 90) -> dict:
    """Build analytics for the current window and persist a proposed setting set."""
    window = _window_days(window_days)
    conn = None
    try:
        conn = db.get_conn()
        with conn:
            active_settings = settings.load_active_settings(force=True)
            rows = fetch_analytics_rows(conn, window)
            metrics = analytics.build_metrics(rows, active_settings)
            proposal = analytics.build_proposed_settings(metrics, active_settings)
            proposed_settings = proposal.get("proposed_settings")
            _normalize_settings(proposed_settings, "proposed_settings")
            metrics = _metrics_with_explainability(metrics, proposal)

            sample_counts = metrics.get("sample_counts", {})
            if not isinstance(sample_counts, Mapping):
                sample_counts = {}

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    INSERT INTO {db.calibration_proposals_table_name()} (
                        window_days,
                        confidence,
                        sample_counts,
                        metrics,
                        proposed_settings,
                        rationale
                    )
                    VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                    RETURNING *
                    """,
                    (
                        window,
                        str(proposal.get("confidence") or "low"),
                        _jsonb(sample_counts),
                        _jsonb(metrics),
                        _jsonb(proposed_settings),
                        _jsonb(proposal.get("rationale") or {}),
                    ),
                )
                return dict(cur.fetchone())
    finally:
        _close(conn)


def apply_proposal(proposal_id: int) -> dict:
    """Apply a proposed setting set and capture the previous active settings."""
    proposal_id = _positive_int(proposal_id, "proposal_id")
    conn = None
    try:
        conn = db.get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                proposal = _lock_proposal(cur, proposal_id)
                if proposal.get("status") != "proposed":
                    raise ProposalStateError(f"Proposal {proposal_id} is not proposed")

                proposed_settings = _normalize_settings(
                    proposal.get("proposed_settings"),
                    "proposed_settings",
                )
                previous_settings = _lock_active_settings(cur)
                _upsert_settings(
                    cur,
                    proposed_settings,
                    active_proposal_id=proposal_id,
                    source="proposal",
                )
                cur.execute(
                    f"""
                    UPDATE {db.calibration_proposals_table_name()}
                    SET
                        status = 'applied',
                        previous_settings = %s::jsonb,
                        applied_at = NOW(),
                        error = NULL
                    WHERE id = %s
                    RETURNING *
                    """,
                    (_jsonb(previous_settings), proposal_id),
                )
                updated = cur.fetchone()
        settings.reset_cache()
        return dict(updated)
    finally:
        _close(conn)


def rollback_proposal(proposal_id: int) -> dict:
    """Restore the settings captured before a proposal was applied."""
    proposal_id = _positive_int(proposal_id, "proposal_id")
    conn = None
    try:
        conn = db.get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                proposal = _lock_proposal(cur, proposal_id)
                if proposal.get("status") != "applied":
                    raise ProposalStateError(f"Proposal {proposal_id} is not applied")

                active_settings = _lock_active_settings(cur)
                if active_settings.get("active_proposal_id") != proposal_id:
                    raise ProposalStateError(f"Proposal {proposal_id} is not the active proposal")

                previous_raw = _mapping_or_error(
                    proposal.get("previous_settings"),
                    "previous_settings",
                )
                previous_settings = _normalize_settings(previous_raw, "previous_settings")
                _upsert_settings(
                    cur,
                    previous_settings,
                    active_proposal_id=_optional_int(previous_raw.get("active_proposal_id")),
                    source=str(previous_raw.get("source") or "rollback"),
                )
                cur.execute(
                    f"""
                    UPDATE {db.calibration_proposals_table_name()}
                    SET
                        status = 'rolled_back',
                        rolled_back_at = NOW(),
                        error = NULL
                    WHERE id = %s
                    RETURNING *
                    """,
                    (proposal_id,),
                )
                updated = cur.fetchone()
        settings.reset_cache()
        return dict(updated)
    finally:
        _close(conn)


def list_proposals(limit: int = 20) -> list[dict]:
    """Return recent calibration proposals."""
    limit = _positive_int(limit, "limit")
    conn = None
    try:
        conn = db.get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT *
                    FROM {db.calibration_proposals_table_name()}
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [dict(row) for row in cur.fetchall()]
    finally:
        _close(conn)


def _lock_proposal(cur, proposal_id: int) -> dict:
    cur.execute(
        f"""
        SELECT *
        FROM {db.calibration_proposals_table_name()}
        WHERE id = %s
        FOR UPDATE
        """,
        (proposal_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ProposalStateError(f"Proposal {proposal_id} was not found")
    return dict(row)


def _lock_active_settings(cur) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT
            active_proposal_id,
            review_low,
            review_high,
            calibration_k,
            calibration_k_batch,
            calibration_min_pool,
            weight_offer,
            weight_interview,
            weight_applied,
            weight_dismiss_note,
            weight_dismiss,
            weight_interested,
            source
        FROM {db.calibration_settings_table_name()}
        WHERE singleton = TRUE
        FOR UPDATE
        """
    )
    row = cur.fetchone()
    if row is None:
        raise ProposalStateError("Active calibration settings row was not found")

    raw = dict(row)
    locked = _normalize_settings(raw, "active_settings")
    locked["source"] = str(raw.get("source") or "db")
    locked["active_proposal_id"] = _optional_int(raw.get("active_proposal_id"))
    return locked


def _upsert_settings(
    cur,
    values: Mapping[str, Any],
    *,
    active_proposal_id: int | None,
    source: str,
) -> None:
    cur.execute(
        f"""
        INSERT INTO {db.calibration_settings_table_name()} (
            singleton,
            active_proposal_id,
            review_low,
            review_high,
            calibration_k,
            calibration_k_batch,
            calibration_min_pool,
            weight_offer,
            weight_interview,
            weight_applied,
            weight_dismiss_note,
            weight_dismiss,
            weight_interested,
            source,
            updated_at
        )
        VALUES (
            TRUE,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            NOW()
        )
        ON CONFLICT (singleton) DO UPDATE SET
            active_proposal_id = EXCLUDED.active_proposal_id,
            review_low = EXCLUDED.review_low,
            review_high = EXCLUDED.review_high,
            calibration_k = EXCLUDED.calibration_k,
            calibration_k_batch = EXCLUDED.calibration_k_batch,
            calibration_min_pool = EXCLUDED.calibration_min_pool,
            weight_offer = EXCLUDED.weight_offer,
            weight_interview = EXCLUDED.weight_interview,
            weight_applied = EXCLUDED.weight_applied,
            weight_dismiss_note = EXCLUDED.weight_dismiss_note,
            weight_dismiss = EXCLUDED.weight_dismiss,
            weight_interested = EXCLUDED.weight_interested,
            source = EXCLUDED.source,
            updated_at = NOW()
        """,
        (
            active_proposal_id,
            values["review_low"],
            values["review_high"],
            values["calibration_k"],
            values["calibration_k_batch"],
            values["calibration_min_pool"],
            values["weight_offer"],
            values["weight_interview"],
            values["weight_applied"],
            values["weight_dismiss_note"],
            values["weight_dismiss"],
            values["weight_interested"],
            source,
        ),
    )


def _normalize_settings(raw: Any, label: str) -> dict[str, Any]:
    data = _mapping_or_error(raw, label)
    out: dict[str, Any] = {}
    for key in _SETTING_KEYS:
        if key not in data:
            raise ProposalStateError(f"{label} missing required setting: {key}")

    for key in _INT_SETTING_KEYS:
        value = _required_int(data[key], f"{label}.{key}")
        if key in {"review_low", "review_high"}:
            if value < 0 or value > 10:
                raise ProposalStateError(f"{label}.{key} must be between 0 and 10")
        elif value <= 0:
            raise ProposalStateError(f"{label}.{key} must be positive")
        out[key] = value

    if out["review_low"] > out["review_high"]:
        raise ProposalStateError(f"{label}.review_low cannot exceed review_high")

    for key in _WEIGHT_SETTING_KEYS:
        out[key] = _required_weight(data[key], f"{label}.{key}")

    return out


def _mapping_or_error(raw: Any, label: str) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProposalStateError(f"{label} is not valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise ProposalStateError(f"{label} is missing")
    return dict(raw)


def _required_int(value: Any, label: str) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ProposalStateError(f"{label} must be an integer") from exc
    return out


def _required_weight(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ProposalStateError(f"{label} must be numeric") from exc
    if not math.isfinite(out) or out <= 0:
        raise ProposalStateError(f"{label} must be positive and finite")
    return out


def _positive_int(value: Any, label: str) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ProposalStateError(f"{label} must be an integer") from exc
    if out <= 0:
        raise ProposalStateError(f"{label} must be positive")
    return out


def _window_days(value: Any) -> int:
    out = _positive_int(value, "window_days")
    if out > MAX_WINDOW_DAYS:
        raise ProposalStateError(f"window_days must be at most {MAX_WINDOW_DAYS}")
    return out


def _metrics_with_explainability(metrics: Any, proposal: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(metrics) if isinstance(metrics, Mapping) else {}
    explainability = {}
    guards = proposal.get("guards")
    evidence = proposal.get("evidence")
    if isinstance(guards, Mapping):
        explainability["guards"] = dict(guards)
    if isinstance(evidence, Mapping):
        explainability["evidence"] = dict(evidence)
    if explainability:
        out["proposal"] = explainability
    return out


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _jsonb(value: Any) -> str:
    return json.dumps(value, default=str)


def _close(conn) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass
