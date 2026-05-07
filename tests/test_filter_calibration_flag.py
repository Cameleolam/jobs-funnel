"""Phase 1 filter change: flag jobs scored without calibration embedding.

We don't invoke claude -p in tests; we patch subprocess.run to return a
known JSON payload, then assert filter.py merges scored_uncalibrated into
the output for jobs where _embedding_calibration_present is False.
"""
import base64
import json
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
