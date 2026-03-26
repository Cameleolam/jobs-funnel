"""Jobs Funnel — lightweight review UI.

Start:
    cd D:/projects/jobs_funnel
    python -m uvicorn ui.server:app --port 8080 --reload
"""

import os
import re

from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ── Config ───────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_CONF = dict(
    host=os.environ.get("JOBS_FUNNEL_PG_HOST", "localhost"),
    port=os.environ.get("JOBS_FUNNEL_PG_PORT", "5432"),
    dbname=os.environ.get("JOBS_FUNNEL_PG_DATABASE", "jobs_funnel"),
    user=os.environ.get("JOBS_FUNNEL_PG_USER", "postgres"),
    password=os.environ.get("JOBS_FUNNEL_PG_PASSWORD", ""),
)
TABLE = os.environ.get("JOBS_FUNNEL_TABLE", "jobs")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="Jobs Funnel UI")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def html_to_text(value):
    if not value:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', str(value))
    text = re.sub(r'</(?:p|div|li|tr|h[1-6])>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


templates.env.filters["html_to_text"] = html_to_text


def render(request: Request, name: str, ctx: dict | None = None):
    context = {"request": request, **(ctx or {})}
    return templates.TemplateResponse(request=request, name=name, context=context)


# ── DB helpers ───────────────────────────────────────────────────────
@contextmanager
def get_db():
    conn = psycopg2.connect(**DB_CONF)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def fetch_all(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetch_one(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def execute(query: str, params: tuple = ()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


# ── Stats helper ─────────────────────────────────────────────────────
def get_stats():
    rows = fetch_all(
        f"SELECT decision, COUNT(*) as cnt FROM {TABLE} "
        f"WHERE status = 'analyzed' GROUP BY decision"
    )
    stats = {"total": 0, "PASS": 0, "MAYBE": 0, "SKIP": 0}
    for r in rows:
        stats[r["decision"]] = r["cnt"]
        stats["total"] += r["cnt"]
    pending = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE status = 'pending'"
    )
    stats["pending"] = pending["cnt"] if pending else 0
    return stats


# ── Routes ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return render(request, "jobs.html", {"stats": get_stats()})


@app.get("/jobs", response_class=HTMLResponse)
async def list_jobs(
    request: Request,
    decision: str = Query("", alias="decision"),
    min_score: int = Query(0, alias="min_score"),
    max_score: int = Query(10, alias="max_score"),
    search: str = Query("", alias="search"),
    sort: str = Query("crawled_at", alias="sort"),
    order: str = Query("desc", alias="order"),
    limit: int = Query(50, alias="limit"),
    offset: int = Query(0, alias="offset"),
):
    allowed_sorts = {
        "crawled_at", "fit_score", "company", "title", "location", "decision",
    }
    sort_col = sort if sort in allowed_sorts else "crawled_at"
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    conditions = ["status IN ('analyzed', 'pending')"]
    params: list = []

    if decision:
        conditions.append("decision = %s")
        params.append(decision)
    conditions.append("COALESCE(fit_score, 0) >= %s")
    params.append(min_score)
    conditions.append("COALESCE(fit_score, 0) <= %s")
    params.append(max_score)
    if search:
        conditions.append("(title ILIKE %s OR company ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    query = (
        f"SELECT id, url, title, company, location, source, fit_score, decision, "
        f"cv_variant, reasoning, status, crawled_at "
        f"FROM {TABLE} WHERE {where} "
        f"ORDER BY {sort_col} {sort_dir} LIMIT %s OFFSET %s"
    )
    params.extend([limit, offset])
    jobs = fetch_all(query, tuple(params))

    count_q = f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE {where}"
    total = fetch_one(count_q, tuple(params[:-2]))["cnt"]

    return render(request, "partials/job_rows.html", {
        "jobs": jobs, "total": total, "limit": limit, "offset": offset,
    })


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    job = fetch_one(f"SELECT * FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        return HTMLResponse("<tr><td colspan='8'>Job not found</td></tr>", status_code=404)
    return render(request, "partials/job_detail.html", {"job": job})


@app.patch("/jobs/{job_id}", response_class=HTMLResponse)
async def update_job(request: Request, job_id: int, decision: str = Form(...)):
    if decision not in ("PASS", "SKIP", "MAYBE"):
        return HTMLResponse("Invalid decision", status_code=400)
    execute(
        f"UPDATE {TABLE} SET decision = %s WHERE id = %s",
        (decision, job_id),
    )
    job = fetch_one(
        f"SELECT id, url, title, company, location, source, fit_score, decision, "
        f"cv_variant, reasoning, status, crawled_at FROM {TABLE} WHERE id = %s",
        (job_id,),
    )
    return render(request, "partials/job_row_single.html", {"job": job})


@app.post("/jobs/{job_id}/rescore", response_class=HTMLResponse)
async def rescore_job(request: Request, job_id: int, description: str = Form(...)):
    execute(
        f"UPDATE {TABLE} SET description = %s, status = 'pending', "
        f"analyzed_at = NULL, error = NULL, retry_count = 0, "
        f"sheet_synced = FALSE, sheet_synced_at = NULL WHERE id = %s",
        (description, job_id),
    )
    job = fetch_one(
        f"SELECT id, url, title, company, location, source, fit_score, decision, "
        f"cv_variant, reasoning, status, crawled_at FROM {TABLE} WHERE id = %s",
        (job_id,),
    )
    return render(request, "partials/job_row_single.html", {"job": job})



@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    return render(request, "partials/stats.html", {"stats": get_stats()})
