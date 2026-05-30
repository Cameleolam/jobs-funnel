from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import ui.server as srv
from ui.routes import tracking as tracking_routes


def test_create_event_can_mark_job_rejected(monkeypatch):
    client = TestClient(srv.app)
    event_row = {
        "id": 7,
        "job_id": 42,
        "occurred_at": datetime(2026, 5, 30, 12, tzinfo=timezone.utc),
        "kind": "decision",
        "label": "Rejected",
        "notes": "Rejected after final round",
    }
    fetch_one = MagicMock(side_effect=[{"id": 42}, event_row])
    execute = MagicMock()
    monkeypatch.setattr(tracking_routes, "fetch_one", fetch_one)
    monkeypatch.setattr(tracking_routes, "execute", execute)

    response = client.post("/api/tracking/events", json={
        "job_id": 42,
        "occurred_at": "2026-05-30T12:00:00+00:00",
        "kind": "decision",
        "label": "Rejected",
        "notes": "Rejected after final round",
        "mark_rejected": True,
    })

    assert response.status_code == 200
    assert response.json()["label"] == "Rejected"
    update_sql, update_params = execute.call_args.args
    assert "user_status = 'rejected'" in update_sql
    assert "closed_at = COALESCE(closed_at, NOW())" in update_sql
    assert update_params == (42,)


def test_create_event_without_rejection_flag_does_not_change_job_status(monkeypatch):
    client = TestClient(srv.app)
    event_row = {
        "id": 8,
        "job_id": 42,
        "occurred_at": datetime(2026, 5, 30, 12, tzinfo=timezone.utc),
        "kind": "note",
        "label": "Follow up",
        "notes": None,
    }
    monkeypatch.setattr(
        tracking_routes,
        "fetch_one",
        MagicMock(side_effect=[{"id": 42}, event_row]),
    )
    execute = MagicMock()
    monkeypatch.setattr(tracking_routes, "execute", execute)

    response = client.post("/api/tracking/events", json={
        "job_id": 42,
        "occurred_at": "2026-05-30T12:00:00+00:00",
        "kind": "note",
        "label": "Follow up",
    })

    assert response.status_code == 200
    execute.assert_not_called()

