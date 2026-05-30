from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ui.config import EVENTS_TABLE, TABLE
from ui.db import execute, fetch_all, fetch_one
from ui.rendering import render


router = APIRouter()


@router.get("/tracking", response_class=HTMLResponse)
async def tracking_page(request: Request):
    return render(request, "tracking.html")


def _serialize_job_with_events(row):
    """Shape a joined jobs+events row dict into the API response format."""
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "url": row["url"],
        "location": row["location"],
        "tracked_at": row["tracked_at"].isoformat() if row["tracked_at"] else None,
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
        "user_status": row["user_status"],
        "events": [],
    }


@router.get("/api/tracking/jobs")
async def api_tracking_jobs():
    """Return all tracked jobs with their events embedded.

    Ordered so the job whose latest event is newest appears first.
    Jobs with no events yet sort by tracked_at desc.
    """
    jobs = fetch_all(
        f"SELECT id, title, company, url, location, tracked_at, closed_at, user_status "
        f"FROM {TABLE} WHERE tracked_at IS NOT NULL"
    )
    if not jobs:
        return []
    by_id = {j["id"]: _serialize_job_with_events(j) for j in jobs}

    events = fetch_all(
        f"SELECT id, job_id, occurred_at, kind, label, notes "
        f"FROM {EVENTS_TABLE} WHERE job_id = ANY(%s) "
        f"ORDER BY occurred_at ASC, id ASC",
        (list(by_id.keys()),),
    )
    for ev in events:
        if ev["job_id"] in by_id:
            by_id[ev["job_id"]]["events"].append({
                "id": ev["id"],
                "occurred_at": ev["occurred_at"].isoformat(),
                "kind": ev["kind"],
                "label": ev["label"],
                "notes": ev["notes"],
            })

    def latest_event_ts(job):
        if job["events"]:
            return job["events"][-1]["occurred_at"]
        return job["tracked_at"] or ""

    result = sorted(by_id.values(), key=latest_event_ts, reverse=True)
    return result


@router.post("/api/tracking/jobs/{job_id}/start")
async def api_tracking_start(job_id: int):
    job = fetch_one(f"SELECT id, tracked_at FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["tracked_at"] is None:
        execute(f"UPDATE {TABLE} SET tracked_at = NOW() WHERE id = %s", (job_id,))
        job = fetch_one(f"SELECT tracked_at FROM {TABLE} WHERE id = %s", (job_id,))
    return {"tracked_at": job["tracked_at"].isoformat()}


@router.post("/api/tracking/jobs/{job_id}/stop")
async def api_tracking_stop(job_id: int):
    job = fetch_one(f"SELECT id FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    execute(f"UPDATE {TABLE} SET tracked_at = NULL WHERE id = %s", (job_id,))
    return {}


@router.post("/api/tracking/jobs/{job_id}/close")
async def api_tracking_close(job_id: int):
    job = fetch_one(f"SELECT id, closed_at FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["closed_at"] is None:
        execute(f"UPDATE {TABLE} SET closed_at = NOW() WHERE id = %s", (job_id,))
        job = fetch_one(f"SELECT closed_at FROM {TABLE} WHERE id = %s", (job_id,))
    return {"closed_at": job["closed_at"].isoformat()}


@router.post("/api/tracking/jobs/{job_id}/reopen")
async def api_tracking_reopen(job_id: int):
    job = fetch_one(f"SELECT id FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    execute(f"UPDATE {TABLE} SET closed_at = NULL WHERE id = %s", (job_id,))
    return {}


class EventCreate(BaseModel):
    job_id: int
    occurred_at: str
    kind: str
    label: str
    notes: str | None = None
    mark_rejected: bool = False


class EventUpdate(BaseModel):
    occurred_at: str | None = None
    kind: str | None = None
    label: str | None = None
    notes: str | None = None
    mark_rejected: bool = False


VALID_EVENT_KINDS = {"application", "contact", "interview", "task", "decision", "note"}


def _serialize_event(row):
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "occurred_at": row["occurred_at"].isoformat(),
        "kind": row["kind"],
        "label": row["label"],
        "notes": row["notes"],
    }


def _mark_job_rejected(job_id: int):
    execute(
        f"UPDATE {TABLE} "
        f"SET user_status = 'rejected', "
        f"closed_at = COALESCE(closed_at, NOW()), "
        f"sheet_synced = FALSE "
        f"WHERE id = %s",
        (job_id,),
    )


@router.post("/api/tracking/events")
async def api_create_event(payload: EventCreate):
    if payload.kind not in VALID_EVENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {payload.kind}")
    if not payload.label.strip():
        raise HTTPException(status_code=400, detail="label is required")
    job = fetch_one(f"SELECT id FROM {TABLE} WHERE id = %s", (payload.job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    row = fetch_one(
        f"INSERT INTO {EVENTS_TABLE} (job_id, occurred_at, kind, label, notes) "
        f"VALUES (%s, %s, %s, %s, %s) "
        f"RETURNING id, job_id, occurred_at, kind, label, notes",
        (payload.job_id, payload.occurred_at, payload.kind,
         payload.label.strip(), payload.notes),
    )
    if payload.mark_rejected:
        _mark_job_rejected(payload.job_id)
    return _serialize_event(row)


@router.patch("/api/tracking/events/{event_id}")
async def api_update_event(event_id: int, payload: EventUpdate):
    existing = fetch_one(
        f"SELECT id, job_id, occurred_at, kind, label, notes "
        f"FROM {EVENTS_TABLE} WHERE id = %s", (event_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    if payload.kind is not None and payload.kind not in VALID_EVENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {payload.kind}")

    fields = []
    values: list = []
    for col in ("occurred_at", "kind", "label", "notes"):
        v = getattr(payload, col)
        if v is not None:
            fields.append(f"{col} = %s")
            values.append(v)
    if not fields:
        return _serialize_event(existing)
    values.append(event_id)
    row = fetch_one(
        f"UPDATE {EVENTS_TABLE} SET {', '.join(fields)} WHERE id = %s "
        f"RETURNING id, job_id, occurred_at, kind, label, notes",
        tuple(values),
    )
    if payload.mark_rejected:
        _mark_job_rejected(row["job_id"])
    return _serialize_event(row)


@router.delete("/api/tracking/events/{event_id}")
async def api_delete_event(event_id: int):
    existing = fetch_one(f"SELECT id FROM {EVENTS_TABLE} WHERE id = %s", (event_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    execute(f"DELETE FROM {EVENTS_TABLE} WHERE id = %s", (event_id,))
    return {}
