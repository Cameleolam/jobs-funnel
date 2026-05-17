"""UI-friendly system health checks."""
from __future__ import annotations

from scripts import doctor


def collect_system_health() -> list[dict[str, str]]:
    out = []
    for check in doctor.collect_checks():
        out.append(
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "action": check.action,
            }
        )
    return out
