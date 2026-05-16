import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from scripts import calibration_proposals as proposals
from scripts.calibration_settings import DEFAULT_SETTINGS


def _cursor(rows):
    cur = MagicMock()
    queue = list(rows)
    cur.fetchone.side_effect = lambda: queue.pop(0) if queue else None
    cur.fetchall.side_effect = lambda: queue.pop(0) if queue else []
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def _conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _sql_text(cur):
    return "\n".join(call.args[0] for call in cur.execute.call_args_list)


def _settings_row(**overrides):
    return {**DEFAULT_SETTINGS, "source": "db", "active_proposal_id": None, **overrides}


def test_fetch_analytics_rows_queries_expected_fields_and_tables(monkeypatch):
    rows = [{"id": 1, "title": "Engineer", "fit_score": 8}]
    cur = _cursor([rows])
    conn = _conn(cur)
    monkeypatch.setattr(proposals.db, "table_name", lambda: "jobs_profile")
    monkeypatch.setattr(proposals.db, "events_table_name", lambda: "jobs_profile_events")

    out = proposals.fetch_analytics_rows(conn, window_days=30)

    assert out == rows
    sql = cur.execute.call_args.args[0]
    params = cur.execute.call_args.args[1]
    assert "FROM jobs_profile j" in sql
    assert "jobs_profile_events" in sql
    assert "latest_review" in sql
    assert "%%offer%%" in sql
    assert sql.count("Reviewed:%") >= 2
    for field in (
        "id",
        "title",
        "company",
        "fit_score",
        "decision",
        "user_status",
        "scoring_provider",
        "scoring_model",
        "review_provider",
        "review_model",
        "notes",
        "has_application",
        "has_interview",
        "has_offer_event",
        "has_review_decision",
        "review_label",
    ):
        assert field in sql
    assert 30 in params


def test_generate_proposal_inserts_metrics_and_settings(monkeypatch):
    inserted = {"id": 9, "status": "proposed"}
    cur = _cursor([[{"id": 1, "fit_score": 8}], inserted])
    conn = _conn(cur)
    monkeypatch.setattr(proposals.db, "get_conn", lambda: conn)
    load_active = MagicMock(return_value=DEFAULT_SETTINGS)
    monkeypatch.setattr(proposals.settings, "load_active_settings", load_active)
    monkeypatch.setattr(
        proposals.analytics,
        "build_metrics",
        lambda rows, active: {
            "sample_counts": {"jobs": 1, "review_decisions": 0, "downstream_outcomes": 0},
            "generated_on": date(2026, 5, 16),
        },
    )
    monkeypatch.setattr(
        proposals.analytics,
        "build_proposed_settings",
        lambda metrics, active: {
            "confidence": "low",
            "proposed_settings": active,
            "rationale": {"review_band": "kept"},
        },
    )

    out = proposals.generate_proposal(window_days=90)

    assert out == inserted
    load_active.assert_called_once_with(force=True)
    insert_sql = cur.execute.call_args_list[-1].args[0]
    insert_params = cur.execute.call_args_list[-1].args[1]
    assert "INSERT INTO" in insert_sql
    assert "proposed_settings" in insert_sql
    assert any(
        isinstance(value, str) and '"generated_on": "2026-05-16"' in value
        for value in insert_params
    )
    conn.close.assert_called_once()


def test_generate_proposal_persists_explainability_in_metrics(monkeypatch):
    inserted = {"id": 10, "status": "proposed"}
    cur = _cursor([[{"id": 1, "fit_score": 8}], inserted])
    conn = _conn(cur)
    monkeypatch.setattr(proposals.db, "get_conn", lambda: conn)
    monkeypatch.setattr(
        proposals.settings,
        "load_active_settings",
        MagicMock(return_value=DEFAULT_SETTINGS),
    )
    monkeypatch.setattr(
        proposals.analytics,
        "build_metrics",
        lambda rows, active: {
            "sample_counts": {"jobs": 1, "review_decisions": 1, "downstream_outcomes": 1},
            "score_bands": {"above_review": {"total": 1, "dismissed": 1}},
        },
    )
    monkeypatch.setattr(
        proposals.analytics,
        "build_proposed_settings",
        lambda metrics, active: {
            "confidence": "medium",
            "proposed_settings": active,
            "rationale": {"review_band": "kept"},
            "guards": {
                "projected_review_jobs": 4,
                "projected_review_cap": 5.0,
                "projected_review_cap_rate": 0.05,
            },
            "evidence": {"false_positives": 2, "false_negatives": 1},
        },
    )

    proposals.generate_proposal(window_days=90)

    insert_params = cur.execute.call_args_list[-1].args[1]
    stored_metrics = json.loads(insert_params[3])
    assert stored_metrics["proposal"]["guards"]["projected_review_jobs"] == 4
    assert stored_metrics["proposal"]["evidence"] == {
        "false_positives": 2,
        "false_negatives": 1,
    }


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("fetch_analytics_rows", (MagicMock(), 366)),
        ("generate_proposal", (366,)),
    ],
)
def test_window_days_rejects_values_above_ui_max(call, args):
    with pytest.raises(proposals.ProposalStateError, match="window_days must be at most 365"):
        getattr(proposals, call)(*args)


def test_apply_proposal_captures_previous_settings_and_upserts_active(monkeypatch):
    settings_table = "sentinel_calibration_settings"
    proposed = {
        "id": 7,
        "status": "proposed",
        "proposed_settings": {**DEFAULT_SETTINGS, "review_low": 3},
    }
    current = _settings_row(review_low=4)
    cur = _cursor([proposed, current, {"id": 7, "status": "applied"}])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))
    monkeypatch.setattr(
        proposals.db,
        "calibration_settings_table_name",
        lambda: settings_table,
    )
    load_active = MagicMock(side_effect=AssertionError("apply must not load settings separately"))
    monkeypatch.setattr(proposals.settings, "load_active_settings", load_active)
    reset_cache = MagicMock()
    monkeypatch.setattr(proposals.settings, "reset_cache", reset_cache)

    out = proposals.apply_proposal(7)

    assert out["status"] == "applied"
    load_active.assert_not_called()
    sql_text = _sql_text(cur)
    assert "FOR UPDATE" in sql_text
    assert "previous_settings" in sql_text
    assert "ON CONFLICT (singleton)" in sql_text
    lock_settings_sql = cur.execute.call_args_list[1].args[0]
    assert f"FROM {settings_table}" in lock_settings_sql
    assert "FOR UPDATE" in lock_settings_sql
    update_params = cur.execute.call_args_list[-1].args[1]
    previous_settings = json.loads(update_params[0])
    assert previous_settings["review_low"] == 4
    assert previous_settings["source"] == "db"
    assert previous_settings["active_proposal_id"] is None
    reset_cache.assert_called_once_with()


def test_apply_proposal_rejects_missing_active_settings_row(monkeypatch):
    proposed = {
        "id": 7,
        "status": "proposed",
        "proposed_settings": {**DEFAULT_SETTINGS, "review_low": 3},
    }
    cur = _cursor([proposed, None])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))
    load_active = MagicMock(side_effect=AssertionError("apply must not fall back to env settings"))
    monkeypatch.setattr(proposals.settings, "load_active_settings", load_active)
    reset_cache = MagicMock()
    monkeypatch.setattr(proposals.settings, "reset_cache", reset_cache)

    with pytest.raises(proposals.ProposalStateError):
        proposals.apply_proposal(7)

    load_active.assert_not_called()
    assert "ON CONFLICT (singleton)" not in _sql_text(cur)
    reset_cache.assert_not_called()


def test_apply_proposal_rejects_non_proposed_status(monkeypatch):
    cur = _cursor([{"id": 7, "status": "applied", "proposed_settings": DEFAULT_SETTINGS}])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))

    with pytest.raises(proposals.ProposalStateError):
        proposals.apply_proposal(7)


def test_apply_proposal_rejects_missing_proposal(monkeypatch):
    cur = _cursor([None])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))

    with pytest.raises(proposals.ProposalStateError):
        proposals.apply_proposal(404)


def test_apply_proposal_rejects_incomplete_proposed_settings(monkeypatch):
    proposed = {
        "id": 7,
        "status": "proposed",
        "proposed_settings": {"review_high": DEFAULT_SETTINGS["review_high"]},
    }
    cur = _cursor([proposed])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))
    monkeypatch.setattr(proposals.settings, "load_active_settings", lambda force=False: DEFAULT_SETTINGS)

    with pytest.raises(proposals.ProposalStateError):
        proposals.apply_proposal(7)


def test_rollback_restores_previous_settings(monkeypatch):
    settings_table = "sentinel_calibration_settings"
    applied = {
        "id": 7,
        "status": "applied",
        "previous_settings": {**DEFAULT_SETTINGS, "review_low": 4},
    }
    cur = _cursor([applied, _settings_row(active_proposal_id=7), {"id": 7, "status": "rolled_back"}])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))
    monkeypatch.setattr(
        proposals.db,
        "calibration_settings_table_name",
        lambda: settings_table,
    )
    reset_cache = MagicMock()
    monkeypatch.setattr(proposals.settings, "reset_cache", reset_cache)

    out = proposals.rollback_proposal(7)

    assert out["status"] == "rolled_back"
    sql_text = _sql_text(cur)
    assert "rolled_back_at = NOW()" in sql_text
    assert "ON CONFLICT (singleton)" in sql_text
    lock_settings_sql = cur.execute.call_args_list[1].args[0]
    assert f"FROM {settings_table}" in lock_settings_sql
    assert "FOR UPDATE" in lock_settings_sql
    reset_cache.assert_called_once_with()


def test_rollback_rejects_when_proposal_is_not_active(monkeypatch):
    applied = {
        "id": 7,
        "status": "applied",
        "previous_settings": {**DEFAULT_SETTINGS, "review_low": 4},
    }
    cur = _cursor([applied, _settings_row(active_proposal_id=8)])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))
    reset_cache = MagicMock()
    monkeypatch.setattr(proposals.settings, "reset_cache", reset_cache)

    with pytest.raises(proposals.ProposalStateError):
        proposals.rollback_proposal(7)

    assert "ON CONFLICT (singleton)" not in _sql_text(cur)
    reset_cache.assert_not_called()


def test_rollback_rejects_missing_proposal(monkeypatch):
    cur = _cursor([None])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))

    with pytest.raises(proposals.ProposalStateError):
        proposals.rollback_proposal(404)


def test_rollback_rejects_missing_previous_settings(monkeypatch):
    applied = {"id": 7, "status": "applied", "previous_settings": None}
    cur = _cursor([applied, _settings_row(active_proposal_id=7)])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))

    with pytest.raises(proposals.ProposalStateError):
        proposals.rollback_proposal(7)


def test_rollback_rejects_non_applied_status(monkeypatch):
    proposed = {"id": 7, "status": "proposed", "previous_settings": DEFAULT_SETTINGS}
    cur = _cursor([proposed])
    monkeypatch.setattr(proposals.db, "get_conn", lambda: _conn(cur))

    with pytest.raises(proposals.ProposalStateError):
        proposals.rollback_proposal(7)


def test_list_proposals_orders_recent_first(monkeypatch):
    rows = [{"id": 2}, {"id": 1}]
    cur = _cursor([rows])
    conn = _conn(cur)
    monkeypatch.setattr(proposals.db, "get_conn", lambda: conn)

    out = proposals.list_proposals(limit=5)

    assert out == rows
    sql = cur.execute.call_args.args[0]
    params = cur.execute.call_args.args[1]
    assert "ORDER BY created_at DESC, id DESC" in sql
    assert params == (5,)
    conn.close.assert_called_once()
