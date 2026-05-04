"""Phase 1 filter change: flag jobs scored without calibration embedding.

We don't invoke claude -p in tests; we patch subprocess.run to return a
known JSON payload, then assert filter.py merges scored_uncalibrated into
the output for jobs where _embedding_calibration_present is False.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _fake_claude(stdout):
    r = MagicMock()
    r.returncode = 0
    r.stdout = stdout
    r.stderr = ""
    return r


def _make_profile(tmp_path):
    pro = tmp_path / "profiles" / "test"
    pro.mkdir(parents=True)
    (pro / "filter_prompt.md").write_text("stub", encoding="utf-8")
    return pro


def test_filter_stamps_scored_uncalibrated_on_missing_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")
    pro = _make_profile(tmp_path)

    # Reload filter after env is set; patch its module-level paths.
    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PIPELINE_DIR", tmp_path)
    monkeypatch.setattr(fil, "PROMPT_FILE", pro / "filter_prompt.md")

    # Write job JSON to a temp file and pass via sys.argv (avoids stdin complexity)
    job = {"title": "T", "description": "D", "_embedding_calibration_present": False}
    job_file = tmp_path / "job_input.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["filter.py", str(job_file)])

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


def test_filter_omits_flag_when_calibration_present(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")
    pro = _make_profile(tmp_path)

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PIPELINE_DIR", tmp_path)
    monkeypatch.setattr(fil, "PROMPT_FILE", pro / "filter_prompt.md")

    job = {"title": "T", "description": "D", "_embedding_calibration_present": True}
    job_file = tmp_path / "job_input.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["filter.py", str(job_file)])

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


def test_filter_batch_handles_single_object_response(tmp_path, monkeypatch, capsys):
    # Regression: batch input + Claude returning a single object (not an array)
    # used to crash on assessment[i] indexing before normalization.
    monkeypatch.setenv("JOBS_FUNNEL_PROFILE", "test")
    pro = _make_profile(tmp_path)

    import importlib
    import scripts.filter as fil
    importlib.reload(fil)
    monkeypatch.setattr(fil, "PIPELINE_DIR", tmp_path)
    monkeypatch.setattr(fil, "PROMPT_FILE", pro / "filter_prompt.md")

    batch = [
        {"title": "A", "description": "D", "_embedding_calibration_present": False},
        {"title": "B", "description": "D", "_embedding_calibration_present": True},
    ]
    job_file = tmp_path / "batch_input.json"
    job_file.write_text(json.dumps(batch), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["filter.py", str(job_file)])

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
