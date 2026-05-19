"""Stats service for the Jobs Funnel UI."""

from ui import schema
from ui.config import TABLE
from ui.db import fetch_all, fetch_one


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
    if schema.HAS_EMBEDDING_COLUMNS:
        awaiting = fetch_one(
            f"SELECT COUNT(*) as cnt FROM {TABLE} "
            f"WHERE embedding IS NULL AND (error_code IS NULL OR error_code != 'EMBED_FAILED')"
        )
        stats["awaiting_embedding"] = awaiting["cnt"] if awaiting else 0
    else:
        stats["awaiting_embedding"] = 0
    return stats
