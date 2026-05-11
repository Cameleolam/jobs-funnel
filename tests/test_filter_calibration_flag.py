"""Phase 1 filter change: flag jobs scored without calibration embedding.

We don't invoke claude -p in tests; we patch subprocess.run to return a
known JSON payload, then assert filter.py merges scored_uncalibrated into
the output for jobs where _embedding_calibration_present is False.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


FIXTURES = Path(__file__).resolve().parent / "fixtures"
FILTER_PROMPT = FIXTURES / "filter_prompt.md"


def _fake_claude(stdout):
    r = MagicMock()
    r.returncode = 0
    r.stdout = stdout
    r.stderr = ""
    return r


def _argv_for_payload(payload):
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return ["filter.py", "--base64", encoded]


def test_filter_stamps_scored_uncalibrated_on_missing_flag(monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    # Reload filter after env is set; patch its module-level paths.
    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)

    job = {"title": "T", "description": "D", "_embedding_calibration_present": False}
    monkeypatch.setattr(sys, "argv", _argv_for_payload(job))

    fake_response = json.dumps({"result": json.dumps({
        "fit_score": 50, "decision": "MAYBE", "cv_variant": "default",
        "hard_blockers": [], "soft_gaps": [], "strong_matches": [],
        "reasoning": "ok", "priority_notes": None
    })})
    with patch.object(subprocess, "run", return_value=_fake_claude(fake_response)):
        # filter.main() may sys.exit; capture either path
        try:
            fil.main()
        except SystemExit:
            pass
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload.get("scored_uncalibrated") is True


def test_filter_omits_flag_when_calibration_present(monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)

    job = {"title": "T", "description": "D", "_embedding_calibration_present": True}
    monkeypatch.setattr(sys, "argv", _argv_for_payload(job))

    fake_response = json.dumps({"result": json.dumps({
        "fit_score": 80, "decision": "PASS", "cv_variant": "default",
        "hard_blockers": [], "soft_gaps": [], "strong_matches": [],
        "reasoning": "ok", "priority_notes": None
    })})
    with patch.object(subprocess, "run", return_value=_fake_claude(fake_response)):
        try:
            fil.main()
        except SystemExit:
            pass
    out = capsys.readouterr().out
    payload = json.loads(out)
    # flag absent OR explicitly false (filter only adds it when False per spec)
    assert payload.get("scored_uncalibrated", False) is False


def test_filter_batch_handles_single_object_response(monkeypatch, capsys):
    # Regression: batch input + Claude returning a single object (not an array)
    # used to crash on assessment[i] indexing before normalization.
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)

    batch = [
        {"title": "A", "description": "D", "_embedding_calibration_present": False},
        {"title": "B", "description": "D", "_embedding_calibration_present": True},
    ]
    monkeypatch.setattr(sys, "argv", _argv_for_payload(batch))

    # Claude returns a single object instead of the requested array
    single_object = json.dumps({
        "fit_score": 60, "decision": "MAYBE", "cv_variant": "default",
        "hard_blockers": [], "soft_gaps": [], "strong_matches": [],
        "reasoning": "ok", "priority_notes": None,
    })
    fake_response = json.dumps({"result": single_object})
    with patch.object(subprocess, "run", return_value=_fake_claude(fake_response)):
        try:
            fil.main()
        except SystemExit:
            pass
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert len(payload) == 2
    # First job had calibration_present=False so the flag should be stamped
    assert payload[0].get("scored_uncalibrated") is True
    # Second is BATCH_PADDING (Claude returned only one)
    assert payload[1].get("error_code") == "BATCH_PADDING"


def test_filter_script_direct_invocation_keeps_package_import_working():
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["JOBS_FUNNEL_PROFILE"] = "profile1"

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "filter.py")],
        input="",
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 1
    assert "No input provided on stdin" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_filter_prompt_is_byte_identical_when_no_calibration_anchors(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil.retrieval, "retrieve_similar_decisions", lambda job: [])

    prompt = "BASE PROMPT"
    job = {"title": "T", "_embedding_calibration_present": True}

    assert fil._system_prompt_with_calibration(prompt, job, is_batch=False) is prompt


def test_filter_skips_retrieval_for_jobs_without_calibration_vector(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    retrieve = MagicMock(return_value=[{"id": 1}])
    monkeypatch.setattr(fil.retrieval, "retrieve_similar_decisions", retrieve)

    prompt = "BASE PROMPT"
    job = {"title": "T", "_embedding_calibration_present": False}

    assert fil._system_prompt_with_calibration(prompt, job, is_batch=False) is prompt
    retrieve.assert_not_called()


def test_filter_merges_batch_calibration_anchors(monkeypatch):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    calls = []

    def fake_retrieve(job):
        calls.append(job["title"])
        return [{
            "id": len(calls),
            "title": "Historical " + job["title"],
            "company": "Acme",
            "fit_score": 80,
            "calibration_label": "applied",
            "notes": "useful anchor",
            "reasoning": "",
            "reached_interview": False,
            "received_offer": False,
            "weighted_score": 0.9,
        }]

    monkeypatch.setattr(fil.retrieval, "retrieve_similar_decisions", fake_retrieve)
    monkeypatch.setattr(fil.retrieval, "calibration_k_batch", lambda: 6)

    prompt = fil._system_prompt_with_calibration(
        "BASE PROMPT",
        [
            {"title": "A", "_embedding_calibration_present": True},
            {"title": "B", "_embedding_calibration_present": True},
        ],
        is_batch=True,
    )

    assert calls == ["A", "B"]
    assert "BASE PROMPT" in prompt
    assert "CALIBRATION - here's how you handled similar jobs in the past." in prompt
    assert "Historical A @ Acme" in prompt
    assert "Historical B @ Acme" in prompt


def test_filter_passes_calibration_block_to_claude_system_prompt(monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)
    monkeypatch.setattr(
        fil.retrieval,
        "retrieve_similar_decisions",
        lambda job: [{
            "id": 10,
            "title": "Backend Engineer",
            "company": "Acme",
            "fit_score": 82,
            "calibration_label": "applied",
            "notes": "interviewed after backend-focused pitch",
            "reasoning": "",
            "reached_interview": True,
            "received_offer": False,
            "weighted_score": 0.95,
        }],
    )

    job = {"title": "T", "description": "D", "_embedding_calibration_present": True}
    monkeypatch.setattr(sys, "argv", _argv_for_payload(job))

    fake_response = json.dumps({"result": json.dumps({
        "fit_score": 80,
        "decision": "PASS",
        "cv_variant": "default",
        "hard_blockers": [],
        "soft_gaps": [],
        "strong_matches": [],
        "reasoning": "ok",
        "priority_notes": None,
    })})
    seen_prompt = {}

    def fake_run(cmd, **kwargs):
        idx = cmd.index("--append-system-prompt")
        seen_prompt["system"] = cmd[idx + 1]
        return _fake_claude(fake_response)

    with patch.object(subprocess, "run", side_effect=fake_run):
        fil.main()

    assert "CALIBRATION - here's how you handled similar jobs in the past." in seen_prompt["system"]
    assert "Backend Engineer @ Acme" in seen_prompt["system"]
    assert "Your note: interviewed after backend-focused pitch" in seen_prompt["system"]
    json.loads(capsys.readouterr().out)


def test_filter_repairs_single_quoted_json_property_from_claude(monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PROMPT_FILE", FILTER_PROMPT)
    monkeypatch.setattr(fil.retrieval, "retrieve_similar_decisions", lambda job: [])

    job = {"title": "T", "description": "D", "_embedding_calibration_present": True}
    monkeypatch.setattr(sys, "argv", _argv_for_payload(job))

    claude_result = """```json
[
  {
    "fit_score": 2,
    "decision": "SKIP",
    "cv_variant": "software",
    "hard_blockers": [],
    "soft_gaps": [],
    "strong_matches": [],
    "reasoning": "ok",
    "priority_notes": null,
    "extracted_salary_min": null,
    'extracted_salary_max': null,
    "extracted_salary_currency": "EUR"
  }
]
```"""
    fake_response = json.dumps({"result": claude_result})

    with patch.object(subprocess, "run", return_value=_fake_claude(fake_response)):
        fil.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["fit_score"] == 2
    assert payload[0]["extracted_salary_max"] is None
    assert payload[0].get("error_code") != "PARSE_FAIL"
