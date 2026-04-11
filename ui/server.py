"""Jobs Funnel — lightweight review UI.

Start:
    cd D:/projects/jobs_funnel
    python -m uvicorn ui.server:app --port 8080 --reload
"""

import io
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

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

# ── Row columns selected for list views ──────────────────────────────
ROW_COLS = (
    "id, url, title, company, location, source, fit_score, decision, "
    "cv_variant, reasoning, status, crawled_at, analyzed_at, "
    "salary_min, salary_max, salary_currency, remote, likely_english, "
    "tags, priority_notes, notes, user_status, "
    "posted_at, employment_type, seniority_level, start_date, "
    "error, error_code, retry_count, "
    "possible_duplicate_of, duplicate_confirmed"
)


# ── Jinja filters ────────────────────────────────────────────────────
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


def format_salary(job):
    mn, mx = job.get("salary_min"), job.get("salary_max")
    if not mn and not mx:
        return ""
    cur = (job.get("salary_currency") or "EUR").upper()
    sym = {"EUR": "\u20ac", "USD": "$", "CHF": "CHF", "GBP": "\u00a3"}.get(cur, cur)
    if mn and mx:
        return f"{mn // 1000}-{mx // 1000}k {sym}"
    if mn:
        return f"{mn // 1000}k+ {sym}"
    return f"{mx // 1000}k {sym}"


def has_flag(notes):
    if not notes:
        return False
    lower = notes.lower()
    return any(kw in lower for kw in ("manual check", "flag", "fetch full", "fetch the"))


def format_duration(ms):
    if ms is None:
        return "..."
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


templates.env.filters["html_to_text"] = html_to_text
templates.env.filters["format_salary"] = format_salary
templates.env.filters["has_flag"] = has_flag
templates.env.filters["format_duration"] = format_duration


def render(request: Request, name: str, ctx: dict | None = None):
    context = {"request": request, "now": datetime.now().astimezone(), **(ctx or {})}
    return templates.TemplateResponse(request=request, name=name, context=context)


# ── DB helpers ───────────────────────────────────────────────────────
@contextmanager
def get_db():
    try:
        conn = psycopg2.connect(**DB_CONF)
    except psycopg2.OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable")
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
    interested = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE user_status = 'interested'"
    )
    stats["interested"] = interested["cnt"] if interested else 0
    applied = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE user_status IN ('applied', 'in_process', 'offer')"
    )
    stats["applied"] = applied["cnt"] if applied else 0
    dismissed = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE user_status IN ('dismissed', 'rejected')"
    )
    stats["dismissed"] = dismissed["cnt"] if dismissed else 0
    error = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE status = 'error'"
    )
    stats["error"] = error["cnt"] if error else 0
    dead = fetch_one(
        f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE status = 'dead'"
    )
    stats["dead"] = dead["cnt"] if dead else 0
    return stats


# ── Query builder ────────────────────────────────────────────────────
def build_job_filter(decision="", applied="", min_score=0, max_score=10, search="", view=""):
    params: list = []
    if view == "error":
        conditions = ["status = 'error'"]
    elif view == "dead":
        conditions = ["status = 'dead'"]
    elif view == "failed":
        conditions = ["status IN ('error', 'dead')"]
    elif view == "duplicates":
        conditions = ["possible_duplicate_of IS NOT NULL AND duplicate_confirmed IS NULL"]
    else:
        conditions = ["status IN ('analyzed', 'pending')"]
        if decision:
            conditions.append("decision = %s")
            params.append(decision)
        if applied == "pending":
            conditions.append("user_status IS NULL")
        elif applied == "interested":
            conditions.append("user_status = 'interested'")
        elif applied == "applied":
            conditions.append("user_status = 'applied'")
        elif applied == "in_process":
            conditions.append("user_status = 'in_process'")
        elif applied == "offer":
            conditions.append("user_status = 'offer'")
        elif applied == "rejected":
            conditions.append("user_status = 'rejected'")
        elif applied == "dismissed":
            conditions.append("user_status = 'dismissed'")
        conditions.append("COALESCE(fit_score, 0) >= %s")
        params.append(min_score)
        conditions.append("COALESCE(fit_score, 0) <= %s")
        params.append(max_score)
    if search:
        conditions.append("(title ILIKE %s OR company ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    return " AND ".join(conditions), params


# ── Routes ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return render(request, "jobs.html", {"stats": get_stats()})


@app.get("/jobs", response_class=HTMLResponse)
async def list_jobs(
    request: Request,
    decision: str = Query("", alias="decision"),
    applied: str = Query("", alias="applied"),
    min_score: int = Query(0, alias="min_score"),
    max_score: int = Query(10, alias="max_score"),
    search: str = Query("", alias="search"),
    view: str = Query("", alias="view"),
    sort: str = Query("fit_score", alias="sort"),
    order: str = Query("desc", alias="order"),
    limit: int = Query(50, alias="limit"),
    offset: int = Query(0, alias="offset"),
):
    allowed_sorts = {
        "crawled_at", "fit_score", "company", "title", "location",
        "decision", "user_status", "analyzed_at",
    }
    sort_col = sort if sort in allowed_sorts else "fit_score"
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    where, params = build_job_filter(decision, applied, min_score, max_score, search, view)
    # Add id as tiebreaker so pagination is stable (avoids duplicates on Load More)
    order_clause = f"{sort_col} {sort_dir}, id {sort_dir}"
    query = (
        f"SELECT {ROW_COLS} FROM {TABLE} WHERE {where} "
        f"ORDER BY {order_clause} LIMIT %s OFFSET %s"
    )
    params.extend([limit, offset])
    jobs = fetch_all(query, tuple(params))

    count_q = f"SELECT COUNT(*) as cnt FROM {TABLE} WHERE {where}"
    total = fetch_one(count_q, tuple(params[:-2]))["cnt"]

    return render(request, "partials/job_rows.html", {
        "jobs": jobs, "total": total, "limit": limit, "offset": offset,
    })


@app.get("/export")
async def export_excel(
    decision: str = Query(""),
    applied: str = Query(""),
    min_score: int = Query(0),
    max_score: int = Query(10),
    search: str = Query(""),
    view: str = Query(""),
    sort: str = Query("fit_score"),
    order: str = Query("desc"),
):
    allowed_sorts = {
        "crawled_at", "fit_score", "company", "title", "location",
        "decision", "user_status", "analyzed_at",
    }
    sort_col = sort if sort in allowed_sorts else "fit_score"
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    where, params = build_job_filter(decision, applied, min_score, max_score, search, view)
    order_clause = f"{sort_col} {sort_dir}, id {sort_dir}"
    query = (
        f"SELECT {ROW_COLS} FROM {TABLE} WHERE {where} "
        f"ORDER BY {order_clause}"
    )
    jobs = fetch_all(query, tuple(params))

    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"

    headers = [
        "Date", "Fetched At", "Posted", "Source", "Company", "Role", "Location", "Salary",
        "Score", "Decision", "Seniority", "Employment", "Start Date",
        "Blockers", "Strong Matches", "Reasoning", "Status", "Job URL",
        "Notes", "My Notes", "_dbId",
    ]
    header_font = Font(bold=True)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font

    fill_active = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fill_interested = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    fill_action = PatternFill(start_color="FFF7ED", end_color="FFF7ED", fill_type="solid")
    fill_gray = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")

    for row_idx, j in enumerate(jobs, 2):
        score = j["fit_score"] or 0
        us = j["user_status"] or ""
        blockers = "; ".join(j["hard_blockers"]) if j.get("hard_blockers") else ""
        matches = "; ".join(j["strong_matches"]) if j.get("strong_matches") else ""
        salary = format_salary(j)

        crawled = j.get("crawled_at")
        posted = j.get("posted_at")
        values = [
            crawled.strftime("%Y-%m-%d") if crawled else "",
            crawled.strftime("%Y-%m-%d %H:%M:%S UTC") if crawled else "",
            posted.strftime("%Y-%m-%d") if posted else "",
            j.get("source", ""),
            j.get("company", ""),
            j.get("title", ""),
            j.get("location", ""),
            salary,
            score,
            j.get("decision", ""),
            j.get("seniority_level", "") or "",
            j.get("employment_type", "") or "",
            j.get("start_date", "") or "",
            blockers,
            matches,
            j.get("reasoning", ""),
            us,
            j.get("url", ""),
            j.get("priority_notes", "") or "",
            j.get("notes", "") or "",
            j.get("id"),
        ]
        for col, val in enumerate(values, 1):
            ws.cell(row=row_idx, column=col, value=val)

        # Row coloring
        if us in ("applied", "in_process", "offer"):
            fill = fill_active
        elif us == "interested":
            fill = fill_interested
        elif us in ("rejected", "dismissed"):
            fill = fill_gray
        elif score >= 5 and not us:
            fill = fill_action
        else:
            fill = None

        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = fill

    # Auto-width for key columns
    for col in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14]:
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"jobs_export_{timestamp}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    job = fetch_one(f"SELECT * FROM {TABLE} WHERE id = %s", (job_id,))
    if not job:
        return HTMLResponse("<tr><td colspan='9'>Job not found</td></tr>", status_code=404)
    return render(request, "partials/job_detail.html", {"job": job})


@app.patch("/jobs/{job_id}", response_class=HTMLResponse)
async def update_job(request: Request, job_id: int, decision: str = Form(...)):
    if decision not in ("PASS", "SKIP", "MAYBE"):
        return HTMLResponse("Invalid decision", status_code=400)
    execute(
        f"UPDATE {TABLE} SET decision = %s WHERE id = %s",
        (decision, job_id),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.patch("/jobs/{job_id}/status", response_class=HTMLResponse)
async def set_user_status(request: Request, job_id: int, user_status: str = Form(...)):
    valid = ("interested", "applied", "in_process", "offer", "rejected", "dismissed", "")
    if user_status not in valid:
        return HTMLResponse("Invalid status", status_code=400)
    status_val = user_status if user_status else None
    execute(
        f"UPDATE {TABLE} SET user_status = %s, "
        f"applied_at = CASE WHEN %s = 'applied' THEN NOW() ELSE applied_at END, "
        f"sheet_synced = FALSE WHERE id = %s",
        (status_val, status_val, job_id),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.patch("/jobs/{job_id}/notes", response_class=HTMLResponse)
async def update_notes(request: Request, job_id: int, notes: str = Form("")):
    execute(
        f"UPDATE {TABLE} SET notes = %s, sheet_synced = FALSE WHERE id = %s",
        (notes if notes.strip() else None, job_id),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.post("/jobs/{job_id}/rescore", response_class=HTMLResponse)
async def rescore_job(request: Request, job_id: int, description: str = Form(...)):
    execute(
        f"UPDATE {TABLE} SET description = %s, status = 'pending', "
        f"analyzed_at = NULL, error = NULL, retry_count = 0, "
        f"sheet_synced = FALSE, sheet_synced_at = NULL WHERE id = %s",
        (description, job_id),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.post("/jobs/{job_id}/retry", response_class=HTMLResponse)
async def retry_job(request: Request, job_id: int):
    execute(
        f"UPDATE {TABLE} SET status = 'pending', retry_count = 0, "
        f"error = NULL, error_code = NULL WHERE id = %s",
        (job_id,),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.patch("/jobs/{job_id}/duplicate", response_class=HTMLResponse)
async def confirm_duplicate(request: Request, job_id: int, confirmed: str = Form(...)):
    if confirmed not in ("true", "false"):
        return HTMLResponse("Invalid value", status_code=400)
    execute(
        f"UPDATE {TABLE} SET duplicate_confirmed = %s WHERE id = %s",
        (confirmed == "true", job_id),
    )
    job = fetch_one(f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s", (job_id,))
    return render(request, "partials/job_row_single.html", {"job": job})


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    return render(request, "partials/stats.html", {"stats": get_stats()})


# ── Pipeline Runs ────────────────────────────────────────────────────
@app.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request):
    return render(request, "runs.html")


@app.get("/runs/list", response_class=HTMLResponse)
async def runs_list(
    request: Request,
    limit: int = Query(50, alias="limit"),
    offset: int = Query(0, alias="offset"),
):
    runs = fetch_all(
        "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    total = fetch_one("SELECT COUNT(*) as cnt FROM pipeline_runs")["cnt"]
    return render(request, "partials/run_rows.html", {
        "runs": runs, "total": total, "limit": limit, "offset": offset,
    })
