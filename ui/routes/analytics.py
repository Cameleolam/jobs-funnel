"""Analytics shell routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.rendering import render


router = APIRouter()


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return render(request, "analytics.html")


@router.get("/api/analytics/scoring")
async def api_analytics_scoring():
    return {
        "summary": {},
        "buckets": [],
        "decisions": [],
        "user_statuses": [],
        "mismatches": {
            "high_score_dismissed": [],
            "low_score_applied": [],
            "pending_review": [],
        },
    }


@router.get("/api/analytics/funnel")
async def api_analytics_funnel():
    return {
        "summary": {},
        "weeks": [],
        "stuck_jobs": [],
    }


@router.get("/api/analytics/market-shifts")
async def api_analytics_market_shifts():
    return {
        "weeks": [],
        "topics": [],
        "summary": {},
    }
