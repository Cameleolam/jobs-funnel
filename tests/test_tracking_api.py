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
