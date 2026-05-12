"""Unit tests for scripts/embed.py."""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

import scripts.embed as embed_mod


# -------- embed() --------

def _fake_response(payload, status=200):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=r
        )
    else:
        r.raise_for_status.return_value = None
    return r


def test_embed_returns_vector_on_success(monkeypatch):
    vec = [0.1] * 1024
    monkeypatch.setattr(embed_mod, "DIM", 1024)
    with patch("httpx.post", return_value=_fake_response({"embedding": vec})):
        out = embed_mod.embed("hello")
    assert out == vec


def test_embed_raises_on_dim_mismatch(monkeypatch):
    monkeypatch.setattr(embed_mod, "DIM", 1024)
    with patch("httpx.post", return_value=_fake_response({"embedding": [0.1] * 512})):
        with pytest.raises(embed_mod.EmbedError, match="Expected 1024 dims"):
            embed_mod.embed("hello")


def test_embed_raises_on_http_error():
    with patch("httpx.post", return_value=_fake_response({}, status=500)):
        with pytest.raises(embed_mod.EmbedError, match="Ollama call failed"):
            embed_mod.embed("hello")


def test_embed_raises_on_missing_field():
    with patch("httpx.post", return_value=_fake_response({"not_embedding": []})):
        with pytest.raises(embed_mod.EmbedError, match="Ollama call failed"):
            embed_mod.embed("hello")


def test_embed_raises_on_request_error():
    with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(embed_mod.EmbedError, match="Ollama call failed"):
            embed_mod.embed("hello")


# -------- text_for_dedup() --------

def test_text_for_dedup_repeats_title():
    job = {"title": "Backend Dev", "company": "ACME", "description": "Python role."}
    txt = embed_mod.text_for_dedup(job)
    # title should appear twice (weighted)
    assert txt.count("Backend Dev") == 2
    assert "ACME" in txt
    assert "Python role." in txt


def test_text_for_dedup_truncates_description():
    job = {"title": "T", "company": "C", "description": "x" * 5000}
    txt = embed_mod.text_for_dedup(job)
    # description capped at 3000 chars
    assert txt.count("x") == 3000


def test_text_for_dedup_normalizes_description():
    job = {
        "title": "Backend Dev",
        "company": "ACME",
        "description": "<p>Python &amp; APIs</p><p>Find more English Speaking Jobs in Germany on Arbeitnow</p>",
    }
    txt = embed_mod.text_for_dedup(job)
    assert "<p>" not in txt
    assert "Python & APIs" in txt
    assert "English Speaking Jobs in Germany" not in txt


def test_text_for_dedup_handles_missing_fields():
    txt = embed_mod.text_for_dedup({})
    # should not raise; produces a string
    assert isinstance(txt, str)


# -------- text_for_calibration() --------

def test_text_for_calibration_includes_structured_prefix():
    job = {
        "title": "Mid Backend Eng",
        "company": "X",
        "location": "Berlin",
        "remote": True,
        "seniority_level": "mid",
        "employment_type": "full-time",
        "likely_english": False,
        "description": "Some description.",
    }
    txt = embed_mod.text_for_calibration(job)
    assert "TITLE: Mid Backend Eng" in txt
    assert "COMPANY: X" in txt
    assert "LOCATION: Berlin" in txt
    assert "REMOTE: yes" in txt
    assert "SENIORITY: mid" in txt
    assert "EMPLOYMENT: full-time" in txt
    assert "LANGUAGE: german" in txt
    # separator between structured prefix and description
    assert "\n---\n" in txt
    assert "Some description." in txt


def test_text_for_calibration_defaults_for_missing():
    txt = embed_mod.text_for_calibration({})
    assert "REMOTE: no" in txt
    assert "SENIORITY: unspecified" in txt
    assert "EMPLOYMENT: unspecified" in txt
    assert "LANGUAGE: german" in txt


def test_text_for_calibration_normalizes_description():
    job = {
        "title": "Backend Dev",
        "company": "ACME",
        "location": "M\u00c3\u00bcnster",
        "description": "<p>Location: M\u00c3\u00bcnster</p><p>Find Jobs in Germany on Arbeitnow</p>",
    }
    txt = embed_mod.text_for_calibration(job)
    assert "LOCATION: M\u00c3\u00bcnster" in txt
    assert "Location: M\u00fcnster" in txt
    assert "<p>" not in txt
    assert "Jobs in Germany" not in txt


def test_cli_job_id_success(monkeypatch, capsys):
    """CLI mode reads job, computes both embeddings, writes back, prints JSON."""
    from scripts import embed as embed_mod

    fake_job = {
        "id": 42,
        "title": "Mid Backend",
        "company": "X",
        "location": "Berlin",
        "description": "desc",
        "remote": False,
        "seniority_level": "mid",
        "employment_type": "full-time",
        "likely_english": False,
    }
    fake_vec = [0.1] * 1024

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = dict(fake_job)
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)

    monkeypatch.setenv("JOBS_FUNNEL_TABLE", "jobs")
    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: fake_conn)
    monkeypatch.setattr(embed_mod, "embed", lambda txt: fake_vec)

    rc = embed_mod.run_cli(["--job-id", "42"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["job_id"] == 42
    assert payload["status"] == "ok"
    assert payload["dim"] == 1024
    # confirm UPDATE was executed (one of the cur.execute calls had embedding=)
    update_calls = [c for c in fake_cur.execute.call_args_list if "UPDATE" in c.args[0].upper()]
    assert len(update_calls) == 1


def test_cli_job_id_missing_returns_error(monkeypatch, capsys):
    from scripts import embed as embed_mod

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = None
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: fake_conn)

    rc = embed_mod.run_cli(["--job-id", "999"])
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out)
    assert payload["status"] == "error"
    assert "not found" in payload["error"].lower()


def test_cli_job_id_embed_failure_increments_attempts(monkeypatch, capsys):
    from scripts import embed as embed_mod

    fake_job = {"id": 7, "title": "T", "company": "C", "description": "d"}
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = dict(fake_job)
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.__enter__ = MagicMock(return_value=fake_conn)
    fake_conn.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr("scripts.db.get_vector_conn", lambda: fake_conn)

    def boom(_):
        raise embed_mod.EmbedError("ollama down")

    monkeypatch.setattr(embed_mod, "embed", boom)

    rc = embed_mod.run_cli(["--job-id", "7"])
    out = capsys.readouterr().out
    assert rc == 2  # soft-degrade exit code
    payload = json.loads(out)
    assert payload["status"] == "embed_failed"
    # an UPDATE that increments embed_attempts must have run
    update_calls = [c for c in fake_cur.execute.call_args_list if "embed_attempts" in c.args[0]]
    assert len(update_calls) == 1
