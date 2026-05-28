"""Analytics shell routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.rendering import render
from ui.services import funnel_analytics, scoring_insights


router = APIRouter()


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return render(request, "analytics.html")


@router.get("/api/analytics/scoring")
async def api_analytics_scoring():
    return scoring_insights.get_scoring_summary()


@router.get("/api/analytics/funnel")
async def api_analytics_funnel(weeks: str = "12"):
    return funnel_analytics.get_funnel_summary(weeks=weeks)


@router.get("/api/analytics/market-shifts")
async def api_analytics_market_shifts():
    return {
        "weeks": [],
        "topics": [],
        "summary": {},
    }
