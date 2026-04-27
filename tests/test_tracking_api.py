"""Integration tests for the tracking API.

These tests assume a live Postgres database with the schema applied
(see scripts/setup_db.sql). They write to and clean up after themselves.
"""
import os
from datetime import datetime, timezone

import psycopg2
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from ui.server import app  # noqa: E402

TABLE = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    conn = psycopg2.connect(
        host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
        port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
        dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
        user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
        password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
    )
    yield conn
    conn.close()


@pytest.fixture
def sample_tracked_job(db):
    """Create one tracked job with two events. Clean up after."""
    with db, db.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TABLE} (url, title, company, location, source, "
            f"status, tracked_at) VALUES "
            f"(%s, %s, %s, %s, 'manual', 'pending', NOW()) RETURNING id",
            (f"https://test.example/{datetime.now().timestamp()}",
             "Test Engineer", "TestCo", "Berlin"),
        )
        job_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO job_events (job_id, occurred_at, kind, label) VALUES "
            "(%s, %s, 'application', 'Applied'), "
            "(%s, %s, 'interview', 'First call')",
            (job_id, datetime(2026, 3, 1, tzinfo=timezone.utc),
             job_id, datetime(2026, 3, 10, tzinfo=timezone.utc)),
        )
    yield job_id
    with db, db.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (job_id,))


def test_list_tracking_jobs_returns_tracked_with_events(client, sample_tracked_job):
    resp = client.get("/api/tracking/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    target = next((j for j in data if j["id"] == sample_tracked_job), None)
    assert target is not None
    assert target["company"] == "TestCo"
    assert target["title"] == "Test Engineer"
    assert target["tracked_at"] is not None
    assert len(target["events"]) == 2
    kinds = [e["kind"] for e in target["events"]]
    assert "application" in kinds
    assert "interview" in kinds


def test_list_tracking_jobs_excludes_untracked(client, db):
    """Jobs with tracked_at IS NULL must not appear."""
    with db, db.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TABLE} (url, title, company, location, source, status) "
            f"VALUES (%s, 'X', 'Y', 'Z', 'manual', 'pending') RETURNING id",
            (f"https://untracked.example/{datetime.now().timestamp()}",),
        )
        untracked_id = cur.fetchone()[0]
    try:
        resp = client.get("/api/tracking/jobs")
        ids = [j["id"] for j in resp.json()]
        assert untracked_id not in ids
    finally:
        with db, db.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (untracked_id,))


@pytest.fixture
def untracked_job(db):
    """A plain job with tracked_at = NULL. Cleaned up after."""
    with db, db.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TABLE} (url, title, company, location, source, status) "
            f"VALUES (%s, 'Role', 'Co', 'Berlin', 'manual', 'pending') RETURNING id",
            (f"https://newtrack.example/{datetime.now().timestamp()}",),
        )
        job_id = cur.fetchone()[0]
    yield job_id
    with db, db.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (job_id,))


def test_start_tracking_sets_tracked_at(client, db, untracked_job):
    resp = client.post(f"/api/tracking/jobs/{untracked_job}/start")
    assert resp.status_code == 200
    assert resp.json()["tracked_at"] is not None
    with db, db.cursor() as cur:
        cur.execute(f"SELECT tracked_at FROM {TABLE} WHERE id = %s", (untracked_job,))
        assert cur.fetchone()[0] is not None


def test_start_tracking_idempotent(client, db, untracked_job):
    """Calling start twice keeps the original tracked_at."""
    r1 = client.post(f"/api/tracking/jobs/{untracked_job}/start")
    first_ts = r1.json()["tracked_at"]
    r2 = client.post(f"/api/tracking/jobs/{untracked_job}/start")
    assert r2.json()["tracked_at"] == first_ts


def test_stop_tracking_clears_tracked_at(client, db, sample_tracked_job):
    resp = client.post(f"/api/tracking/jobs/{sample_tracked_job}/stop")
    assert resp.status_code == 200
    with db, db.cursor() as cur:
        cur.execute(f"SELECT tracked_at FROM {TABLE} WHERE id = %s", (sample_tracked_job,))
        assert cur.fetchone()[0] is None
        # Events are preserved
        cur.execute("SELECT COUNT(*) FROM job_events WHERE job_id = %s", (sample_tracked_job,))
        assert cur.fetchone()[0] == 2


def test_start_tracking_404_for_missing_job(client):
    resp = client.post("/api/tracking/jobs/99999999/start")
    assert resp.status_code == 404


VALID_KINDS = ("application", "contact", "interview", "task", "decision", "note")


def test_create_event(client, db, sample_tracked_job):
    payload = {
        "job_id": sample_tracked_job,
        "occurred_at": "2026-04-01T09:00:00+00:00",
        "kind": "interview",
        "label": "Tech round",
        "notes": "Whiteboard problem",
    }
    resp = client.post("/api/tracking/events", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] > 0
    assert body["label"] == "Tech round"
    assert body["kind"] == "interview"


def test_create_event_rejects_bad_kind(client, sample_tracked_job):
    resp = client.post("/api/tracking/events", json={
        "job_id": sample_tracked_job,
        "occurred_at": "2026-04-01T09:00:00+00:00",
        "kind": "lunch",
        "label": "x",
    })
    assert resp.status_code == 400


def test_create_event_rejects_missing_job(client):
    resp = client.post("/api/tracking/events", json={
        "job_id": 99999999,
        "occurred_at": "2026-04-01T09:00:00+00:00",
        "kind": "note",
        "label": "x",
    })
    assert resp.status_code == 404


def test_update_event(client, sample_tracked_job, db):
    with db, db.cursor() as cur:
        cur.execute("SELECT id FROM job_events WHERE job_id = %s LIMIT 1",
                    (sample_tracked_job,))
        event_id = cur.fetchone()[0]
    resp = client.patch(f"/api/tracking/events/{event_id}",
                        json={"label": "Updated label"})
    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated label"


def test_delete_event(client, sample_tracked_job, db):
    with db, db.cursor() as cur:
        cur.execute("SELECT id FROM job_events WHERE job_id = %s LIMIT 1",
                    (sample_tracked_job,))
        event_id = cur.fetchone()[0]
    resp = client.delete(f"/api/tracking/events/{event_id}")
    assert resp.status_code == 200
    with db, db.cursor() as cur:
        cur.execute("SELECT id FROM job_events WHERE id = %s", (event_id,))
        assert cur.fetchone() is None
