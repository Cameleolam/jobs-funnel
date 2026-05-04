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
