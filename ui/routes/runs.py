"""Pipeline run UI routes."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ui.db import fetch_all, fetch_one
from ui.rendering import render


router = APIRouter()


@router.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request):
    return render(request, "runs.html")


@router.get("/runs/list", response_class=HTMLResponse)
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
