from decimal import Decimal
from unittest.mock import MagicMock

import scripts.calibration_settings as settings


def setup_function():
    settings.reset_cache()


def test_env_settings_use_current_defaults(monkeypatch):
    for key in settings.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    out = settings.env_settings()

    assert out["review_low"] == 4
    assert out["review_high"] == 6
    assert out["calibration_k"] == 3
    assert out["calibration_k_batch"] == 6
    assert out["calibration_min_pool"] == 3
    assert out["weight_offer"] == 1.5
    assert out["weight_interested"] == 0.7


def test_env_settings_parse_valid_overrides(monkeypatch):
    monkeypatch.setenv("SCORING_REVIEW_LOW", "3")
    monkeypatch.setenv("SCORING_REVIEW_HIGH", "7")
    monkeypatch.setenv("CALIBRATION_K", "4")
    monkeypatch.setenv("WEIGHT_OFFER", "1.8")

    out = settings.env_settings()

    assert out["review_low"] == 3
    assert out["review_high"] == 7
    assert out["calibration_k"] == 4
    assert out["weight_offer"] == 1.8


def test_load_active_settings_falls_back_when_db_fails(monkeypatch):
    monkeypatch.setattr(settings.db, "get_conn", MagicMock(side_effect=RuntimeError("db down")))

    out = settings.load_active_settings(force=True)

    assert out["review_low"] == settings.DEFAULT_SETTINGS["review_low"]
    assert out["source"] == "env"


def test_load_active_settings_reads_db_singleton(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = {
        "review_low": 3,
        "review_high": 7,
        "calibration_k": 4,
        "calibration_k_batch": 8,
        "calibration_min_pool": 5,
        "weight_offer": Decimal("1.8"),
        "weight_interview": Decimal("1.6"),
        "weight_applied": Decimal("1.3"),
        "weight_dismiss_note": Decimal("1.4"),
        "weight_dismiss": Decimal("1.0"),
        "weight_interested": Decimal("0.6"),
        "source": "proposal",
        "active_proposal_id": 12,
    }
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(settings.db, "get_conn", lambda: conn)
    monkeypatch.setattr(settings.db, "calibration_settings_table_name", lambda: "jobs_calibration_settings")

    out = settings.load_active_settings(force=True)

    assert out["review_low"] == 3
    assert out["review_high"] == 7
    assert out["weight_offer"] == 1.8
    assert out["source"] == "proposal"
    assert out["active_proposal_id"] == 12
    assert "FROM jobs_calibration_settings" in cur.execute.call_args.args[0]


def test_accessors_return_expected_shapes(monkeypatch):
    monkeypatch.setattr(
        settings,
        "load_active_settings",
        lambda force=False: {
            **settings.DEFAULT_SETTINGS,
            "review_low": 2,
            "review_high": 8,
            "calibration_k": 5,
            "calibration_k_batch": 9,
            "calibration_min_pool": 6,
            "weight_offer": 1.9,
        },
    )

    assert settings.review_band() == (2, 8)
    assert settings.calibration_k() == 5
    assert settings.calibration_k_batch() == 9
    assert settings.calibration_min_pool() == 6
    assert settings.retrieval_weights()["offer"] == 1.9
