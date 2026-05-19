"""Template setup and rendering helpers for the Jobs Funnel UI."""
import re
from datetime import datetime

from fastapi import Request
from fastapi.templating import Jinja2Templates

from ui.config import TEMPLATES_DIR

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
