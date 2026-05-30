from pathlib import Path


JOBS = Path("ui/templates/jobs.html").read_text(encoding="utf-8")
ROWS = Path("ui/templates/partials/job_rows.html").read_text(encoding="utf-8")
EVENT_MODAL = Path("ui/static/tracking/components/EventModal.js").read_text(encoding="utf-8")


def test_jobs_template_has_review_queue_shortcut():
    assert "Review Queue" in JOBS
    assert 'name="view"' in JOBS
    assert 'value="review"' in JOBS


def test_job_rows_have_empty_state():
    assert "No jobs match these filters." in ROWS


def test_jobs_template_groups_secondary_filters():
    assert "filter-secondary" in JOBS


def test_hide_rejected_checkbox_has_hidden_false_value():
    assert 'name="hide_rejected" value="false"' in JOBS


def test_tracking_event_modal_has_rejection_checkbox():
    assert "Mark this job as rejected" in EVENT_MODAL
    assert "mark_rejected" in EVENT_MODAL
