"""Tests for manual-add form routes."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ui.server import app


@pytest.fixture
def client():
    return TestClient(app)


@patch("ui.server.get_db")
def test_get_new_job_form_renders(mock_db, client):
    response = client.get("/jobs/new")
    assert response.status_code == 200
    assert "Add Job Manually" in response.text
    assert 'name="url"' in response.text
    assert 'name="title"' in response.text
    assert 'name="company"' in response.text
    assert 'name="location"' in response.text
    assert 'name="description"' in response.text


@patch("ui.server.fetch_one")
@patch("ui.server.execute")
def test_post_new_job_inserts_and_redirects(mock_execute, mock_fetch_one, client):
    # First fetch_one call: duplicate-URL check returns None.
    # Second fetch_one call: post-insert lookup returns the new id.
    mock_fetch_one.side_effect = [None, {"id": 42}]

    response = client.post(
        "/jobs/new",
        data={
            "url": "https://example.com/job/1",
            "title": "Frontend Engineer",
            "company": "Acme",
            "location": "Remote EU",
            "description": "A great frontend role.",
            "remote": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?new=42"

    assert mock_execute.call_count == 1
    sql = mock_execute.call_args[0][0]
    assert "INSERT INTO" in sql
    assert "'manual'" in sql  # hard-coded source literal
    params = mock_execute.call_args[0][1]
    assert params[0] == "https://example.com/job/1"
    assert params[1] == "Frontend Engineer"
    assert params[2] == "Acme"
    assert params[3] == "Remote EU"
    assert params[4] == "A great frontend role."
    assert params[5] is True  # remote


@patch("ui.server.fetch_one")
@patch("ui.server.execute")
def test_post_new_job_duplicate_url_redirects_no_insert(mock_execute, mock_fetch_one, client):
    mock_fetch_one.return_value = {"id": 17}

    response = client.post(
        "/jobs/new",
        data={
            "url": "https://example.com/job/1",
            "title": "Frontend Engineer",
            "company": "Acme",
            "location": "Remote",
            "description": "Role desc.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?duplicate=17"
    assert mock_execute.call_count == 0


@patch("ui.server.execute")
@patch("ui.server.fetch_one")
def test_post_new_job_empty_description_rerenders_with_error(mock_fetch_one, mock_execute, client):
    response = client.post(
        "/jobs/new",
        data={
            "url": "https://example.com/job/2",
            "title": "Backend Dev",
            "company": "BigCo",
            "location": "Berlin",
            "description": "   ",
        },
    )
    assert response.status_code == 200
    assert "All required fields must be filled." in response.text
    assert "https://example.com/job/2" in response.text
    assert "BigCo" in response.text
    assert mock_execute.call_count == 0
    assert mock_fetch_one.call_count == 0
