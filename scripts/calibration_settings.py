"""Runtime accessors for active calibration settings."""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import psycopg2.extras
from dotenv import load_dotenv

from scripts import db


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_DOTENV_LOADED = False

INT_ENV_KEYS = {
    "review_low": "SCORING_REVIEW_LOW",
    "review_high": "SCORING_REVIEW_HIGH",
    "calibration_k": "CALIBRATION_K",
    "calibration_k_batch": "CALIBRATION_K_BATCH",
    "calibration_min_pool": "CALIBRATION_MIN_POOL",
}
WEIGHT_ENV_KEYS = {
    "weight_offer": "WEIGHT_OFFER",
    "weight_interview": "WEIGHT_INTERVIEW",
    "weight_applied": "WEIGHT_APPLIED",
    "weight_dismiss_note": "WEIGHT_DISMISS_NOTE",
    "weight_dismiss": "WEIGHT_DISMISS",
    "weight_interested": "WEIGHT_INTERESTED",
}
ENV_KEYS = tuple([*INT_ENV_KEYS.values(), *WEIGHT_ENV_KEYS.values()])

INT_SETTINGS = tuple(INT_ENV_KEYS.keys())
WEIGHT_SETTINGS = tuple(WEIGHT_ENV_KEYS.keys())
REVIEW_BAND_SETTINGS = {"review_low", "review_high"}
_REVIEW_BAND_ERROR_KEY = "_review_band_error"
RETRIEVAL_WEIGHT_KEYS = {
    "offer": "weight_offer",
    "interview": "weight_interview",
    "applied": "weight_applied",
    "dismiss_note": "weight_dismiss_note",
    "dismiss": "weight_dismiss",
    "interested": "weight_interested",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "review_low": 4,
    "review_high": 6,
    "calibration_k": 3,
    "calibration_k_batch": 6,
    "calibration_min_pool": 3,
    "weight_offer": 1.5,
    "weight_interview": 1.4,
    "weight_applied": 1.2,
    "weight_dismiss_note": 1.2,
    "weight_dismiss": 0.8,
    "weight_interested": 0.7,
    "source": "env",
    "active_proposal_id": None,
}

_db_settings: dict[str, Any] | None = None


def _load_env() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv(ENV_PATH)
    _DOTENV_LOADED = True


def reset_cache() -> None:
    global _db_settings
    _db_settings = None


def _coerce_int(value: Any, *, min_value: int = 1, max_value: int | None = None) -> int | None:
    if value is None:
        return None
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    if out < min_value:
        return None
    if max_value is not None and out > max_value:
        return None
    return out


def _coerce_weight(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out) or out <= 0:
        return None
    return out


def env_settings() -> dict[str, Any]:
    _load_env()
    out = dict(DEFAULT_SETTINGS)
    review_band_error: str | None = None

    for key, env_key in INT_ENV_KEYS.items():
        raw = os.environ.get(env_key)
        min_value = 0 if key in REVIEW_BAND_SETTINGS else 1
        parsed = _coerce_int(
            raw,
            min_value=min_value,
            max_value=10 if key in REVIEW_BAND_SETTINGS else None,
        )
        if parsed is None and raw is not None and key in REVIEW_BAND_SETTINGS:
            review_band_error = f"Invalid review band setting: {env_key}"
        out[key] = parsed if parsed is not None else DEFAULT_SETTINGS[key]

    for key, env_key in WEIGHT_ENV_KEYS.items():
        parsed = _coerce_weight(os.environ.get(env_key))
        out[key] = parsed if parsed is not None else DEFAULT_SETTINGS[key]

    if out["review_low"] > out["review_high"]:
        review_band_error = "Invalid review band: SCORING_REVIEW_LOW exceeds SCORING_REVIEW_HIGH"
        out["review_low"] = DEFAULT_SETTINGS["review_low"]
        out["review_high"] = DEFAULT_SETTINGS["review_high"]

    out["source"] = "env"
    out["active_proposal_id"] = None
    if review_band_error:
        out[_REVIEW_BAND_ERROR_KEY] = review_band_error
    return out


def _normalize_db_settings(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    out = dict(DEFAULT_SETTINGS)
    for key in INT_SETTINGS:
        min_value = 0 if key in REVIEW_BAND_SETTINGS else 1
        parsed = _coerce_int(
            row.get(key),
            min_value=min_value,
            max_value=10 if key in REVIEW_BAND_SETTINGS else None,
        )
        if parsed is None:
            return None
        out[key] = parsed

    for key in WEIGHT_SETTINGS:
        parsed = _coerce_weight(row.get(key))
        if parsed is None:
            return None
        out[key] = parsed

    if out["review_low"] > out["review_high"]:
        return None

    out["source"] = str(row.get("source") or "db")
    out["active_proposal_id"] = row.get("active_proposal_id")
    return out


def _load_db_settings(fallback: dict[str, Any]) -> dict[str, Any] | None:
    conn = None
    try:
        table = db.calibration_settings_table_name()
        conn = db.get_conn()
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
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
                        active_proposal_id
                    FROM {table}
                    WHERE singleton = TRUE
                    LIMIT 1
                    """
                )
                return _normalize_db_settings(cur.fetchone())
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def load_active_settings(force: bool = False) -> dict[str, Any]:
    global _db_settings
    if _db_settings is not None and not force:
        return dict(_db_settings)

    fallback = env_settings()
    active = _load_db_settings(fallback) or fallback
    _db_settings = dict(active)
    return dict(active)


def review_band() -> tuple[int, int]:
    settings = load_active_settings()
    if settings.get(_REVIEW_BAND_ERROR_KEY):
        raise ValueError(settings[_REVIEW_BAND_ERROR_KEY])
    return int(settings["review_low"]), int(settings["review_high"])


def calibration_k() -> int:
    return int(load_active_settings()["calibration_k"])


def calibration_min_pool() -> int:
    return int(load_active_settings()["calibration_min_pool"])


def calibration_k_batch() -> int:
    return int(load_active_settings()["calibration_k_batch"])


def retrieval_weights() -> dict[str, float]:
    settings = load_active_settings()
    return {name: float(settings[key]) for name, key in RETRIEVAL_WEIGHT_KEYS.items()}
