import base64
import json
import subprocess
import sys

import pytest

from scripts import run_filter


def _batch_payload(count):
    return [{"title": f"Job {idx}"} for idx in range(count)]


def _assert_timeout_fallbacks(payload, count):
    assert isinstance(payload, list)
    assert len(payload) == count
    for item in payload:
        assert item["fit_score"] == 0
        assert item["decision"] == "SKIP"
        assert item["error_code"] == "TIMEOUT"
        assert any("timed out" in blocker.lower() for blocker in item["hard_blockers"])


def test_run_filter_file_timeout_returns_fallback_for_each_batch_item(monkeypatch, capsys, tmp_path):
    batch = _batch_payload(3)
    input_path = tmp_path / "batch.json"
    input_path.write_text(json.dumps(batch), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_filter.py", str(tmp_path), "--file", str(input_path)])
    monkeypatch.setattr(run_filter.time, "sleep", lambda seconds: None)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(run_filter.subprocess, "run", raise_timeout)

    run_filter.main()

    payload = json.loads(capsys.readouterr().out)
    _assert_timeout_fallbacks(payload, 3)


def test_run_filter_legacy_base64_timeout_returns_fallback_for_each_batch_item(monkeypatch, capsys, tmp_path):
    batch = _batch_payload(2)
    encoded = base64.b64encode(json.dumps(batch).encode("utf-8")).decode("ascii")
    monkeypatch.setattr(sys, "argv", ["run_filter.py", str(tmp_path), encoded])
    monkeypatch.setattr(run_filter.time, "sleep", lambda seconds: None)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(run_filter.subprocess, "run", raise_timeout)

    run_filter.main()

    payload = json.loads(capsys.readouterr().out)
    _assert_timeout_fallbacks(payload, 2)


def test_run_filter_uses_configurable_wrapper_timeout(monkeypatch, capsys, tmp_path):
    input_path = tmp_path / "job.json"
    input_path.write_text(json.dumps({"title": "A"}), encoding="utf-8")
    monkeypatch.setenv("SCORING_WRAPPER_TIMEOUT_SECONDS", "1234")
    monkeypatch.setattr(sys, "argv", ["run_filter.py", str(tmp_path), "--file", str(input_path)])
    monkeypatch.setattr(run_filter.time, "sleep", lambda seconds: None)
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        result = subprocess.CompletedProcess(args[0], 0, stdout='{"fit_score": 8}', stderr="")
        return result

    monkeypatch.setattr(run_filter.subprocess, "run", fake_run)

    run_filter.main()

    assert seen["timeout"] == 1234
    assert json.loads(capsys.readouterr().out)["fit_score"] == 8
