from ui.services.scoring_insights import build_scoring_summary


def test_build_scoring_summary_counts_buckets_and_mismatches():
    rows = [
        {
            "id": 1,
            "title": "Staff Engineer",
            "company": "Acme",
            "fit_score": "9",
            "decision": "recommended",
            "user_status": "dismissed",
        },
        {
            "id": 2,
            "title": "Backend Engineer",
            "company": "Beta",
            "fit_score": 4,
            "decision": "recommended",
            "user_status": "applied",
        },
        {
            "id": 3,
            "title": "Data Engineer",
            "company": "Core",
            "fit_score": "5.0",
            "decision": "pending_review",
            "user_status": "interested",
        },
        {
            "id": 4,
            "title": "Platform Engineer",
            "company": "Delta",
            "fit_score": None,
            "decision": "pending_review",
            "user_status": "new",
        },
        {
            "id": 5,
            "title": "Invalid Score",
            "company": "Echo",
            "fit_score": "not-a-number",
            "decision": "recommended",
            "user_status": "dismissed",
        },
    ]

    summary = build_scoring_summary(rows, has_human_review_columns=False)

    assert summary["summary"] == {
        "total": 5,
        "applied": 1,
        "dismissed": 2,
        "pending_review": 2,
        "needs_human_review": 0,
        "low_confidence": 0,
        "high_score_dismissed": 1,
        "low_score_applied": 2,
    }
    assert summary["buckets"] == [
        {
            "bucket": "0-2",
            "total": 0,
            "applied": 0,
            "dismissed": 0,
            "application_rate": 0.0,
            "dismissed_rate": 0.0,
        },
        {
            "bucket": "3-5",
            "total": 2,
            "applied": 1,
            "dismissed": 0,
            "application_rate": 0.5,
            "dismissed_rate": 0.0,
        },
        {
            "bucket": "6-8",
            "total": 0,
            "applied": 0,
            "dismissed": 0,
            "application_rate": 0.0,
            "dismissed_rate": 0.0,
        },
        {
            "bucket": "9-10",
            "total": 1,
            "applied": 0,
            "dismissed": 1,
            "application_rate": 0.0,
            "dismissed_rate": 1.0,
        },
    ]
    assert summary["decisions"] == [
        {"decision": "recommended", "count": 3},
        {"decision": "pending_review", "count": 2},
    ]
    assert summary["user_statuses"] == [
        {"user_status": "dismissed", "count": 2},
        {"user_status": "applied", "count": 1},
        {"user_status": "interested", "count": 1},
        {"user_status": "new", "count": 1},
    ]
    assert summary["mismatches"]["high_score_dismissed"] == [
        {
            "id": 1,
            "title": "Staff Engineer",
            "company": "Acme",
            "fit_score": 9.0,
            "decision": "recommended",
            "user_status": "dismissed",
        }
    ]
    assert [row["id"] for row in summary["mismatches"]["low_score_applied"]] == [2, 3]
    assert [row["id"] for row in summary["mismatches"]["pending_review"]] == [3, 4]


def test_build_scoring_summary_uses_optional_human_review_fields_when_available():
    rows = [
        {
            "id": 6,
            "title": "ML Engineer",
            "company": "Foxtrot",
            "fit_score": 8,
            "decision": "recommended",
            "user_status": "new",
            "needs_human_review": True,
            "confidence": "0.4",
        },
        {
            "id": 7,
            "title": "Frontend Engineer",
            "company": "Gamma",
            "fit_score": 7,
            "decision": "recommended",
            "user_status": "new",
            "needs_human_review": False,
            "confidence": 0.8,
        },
    ]

    summary = build_scoring_summary(rows, has_human_review_columns=True)

    assert summary["summary"]["pending_review"] == 1
    assert summary["summary"]["needs_human_review"] == 1
    assert summary["summary"]["low_confidence"] == 1
    assert [row["id"] for row in summary["mismatches"]["pending_review"]] == [6]
