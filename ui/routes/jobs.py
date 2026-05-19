"""Job route query helpers."""

from ui import schema


def build_order_clause(sort_col: str, sort_dir: str, view: str = "") -> str:
    if view == "review":
        return "COALESCE(fit_score, 0) DESC, analyzed_at DESC NULLS LAST, id DESC"
    return f"{sort_col} {sort_dir}, id {sort_dir}"


def build_job_filter(decision="", applied="", min_score=0, max_score=10, search="", view="",
                     hide_staffing=False, hide_geo=False, english_only=False,
                     hide_rejected=False, recent_only=True):
    params: list = []
    if view == "error":
        conditions = ["status = 'error'"]
    elif view == "dead":
        conditions = ["status = 'dead'"]
    elif view == "failed":
        conditions = ["status IN ('error', 'dead')"]
    elif view == "duplicates":
        conditions = ["possible_duplicate_of IS NOT NULL AND duplicate_confirmed IS NULL"]
    elif view == "review":
        if schema.HAS_HUMAN_REVIEW_COLUMNS:
            conditions = ["status = 'analyzed' AND (needs_human_review = TRUE OR decision = 'pending_review')"]
        else:
            conditions = ["status = 'analyzed' AND decision = 'pending_review'"]
    else:
        conditions = ["status IN ('analyzed', 'pending')"]
        if recent_only:
            conditions.append("crawled_at >= NOW() - INTERVAL '10 days'")
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
    if hide_staffing:
        conditions.append("staffing_agency = FALSE")
    if hide_geo:
        conditions.append("geo_mismatch = FALSE")
    if english_only:
        conditions.append("likely_english = TRUE")
    if hide_rejected:
        conditions.append("(user_status IS NULL OR user_status NOT IN ('rejected', 'dismissed'))")
    return " AND ".join(conditions), params
