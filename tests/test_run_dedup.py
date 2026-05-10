"""Tests for scripts/run_dedup.py."""
import json
import subprocess
import sys
from pathlib import Path

import scripts.run_dedup as rd
from scripts.dedup import DedupDecision


REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_METRICS = {"vector_resolved": 0, "claude_calls": 0, "duplicates": 0}


def test_run_dedup_outputs_pairs_and_metrics(tmp_path, monkeypatch):
    payload = {"new_jobs": [{"id": 10}, {"id": 11}]}
    path = tmp_path / "dedup.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    decisions = [
        DedupDecision(10, 5, "vector_certain", 0.97, "high", "same role"),
        DedupDecision(11, None, "vector_clear", 0.70),
    ]
    monkeypatch.setattr(rd.dedup, "find_duplicate_by_id", lambda job_id: decisions.pop(0))

    out = rd.run([str(path)])

    assert out["pairs"][0]["new_id"] == 10
    assert out["pairs"][0]["existing_id"] == 5
    assert out["metrics"]["vector_resolved"] == 2
    assert out["metrics"]["claude_calls"] == 0
    assert not path.exists()


def test_run_dedup_counts_claude_paths(tmp_path, monkeypatch):
    path = tmp_path / "dedup.json"
    path.write_text(json.dumps({"new_jobs": [{"id": 10}]}), encoding="utf-8")
    monkeypatch.setattr(
        rd.dedup,
        "find_duplicate_by_id",
        lambda job_id: DedupDecision(10, 5, "claude_dup", 0.90, "medium", "same role"),
    )

    out = rd.run([str(path)])

    assert out["metrics"]["vector_resolved"] == 0
    assert out["metrics"]["claude_calls"] == 1


def test_run_dedup_direct_invocation_no_args_outputs_empty_json():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_dedup.py")],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT.parent),
    )

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["pairs"] == []
    assert out["metrics"] == ZERO_METRICS
