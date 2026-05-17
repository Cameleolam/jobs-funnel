from pathlib import Path


JOBS = Path("ui/templates/jobs.html").read_text(encoding="utf-8")
ROWS = Path("ui/templates/partials/job_rows.html").read_text(encoding="utf-8")


def test_jobs_template_has_review_queue_shortcut():
    assert "Review Queue" in JOBS
    assert 'name="view"' in JOBS
    assert 'value="review"' in JOBS


def test_job_rows_have_empty_state():
    assert "No jobs match these filters." in ROWS


def test_jobs_template_groups_secondary_filters():
    assert "filter-secondary" in JOBS
