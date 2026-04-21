"""Tests for scripts.build_workflow registry-driven crawler emission."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent


def run_build(profile: str):
    env = os.environ.copy()
    env["JOBS_FUNNEL_PROFILE"] = profile
    result = subprocess.run(
        [sys.executable, "scripts/build_workflow.py"],
        cwd=REPO, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, f"build failed: stdout={result.stdout}\nstderr={result.stderr}"
    return json.loads((REPO / "workflow.json").read_text(encoding="utf-8"))


def test_build_emits_all_five_crawlers_for_profile1():
    wf = run_build("profile1")
    node_names = {n["name"] for n in wf["nodes"]}
    assert "AA: Fetch Jobs" in node_names
    assert "AN: Fetch & Filter" in node_names
    assert "Remotive: Fetch & Filter" in node_names
    assert "AN Remote: Fetch & Filter" in node_names
    assert "Himalayas: Fetch & Filter" in node_names


def test_merge_sources_number_inputs_matches_crawler_count():
    wf = run_build("profile1")
    merge = next(n for n in wf["nodes"] if n["name"] == "Merge Sources")
    assert merge["parameters"]["numberInputs"] == 5


def test_db_run_start_fans_out_to_all_crawlers():
    wf = run_build("profile1")
    fanout = wf["connections"]["DB: Run Start"]["main"][0]
    target_names = {c["node"] for c in fanout}
    assert len(fanout) == 5
    assert "AA: Fetch Jobs" in target_names
    assert "Himalayas: Fetch & Filter" in target_names


def test_each_crawler_connects_to_merge_sources_with_unique_index():
    wf = run_build("profile1")
    indexes = []
    for crawler in [
        "AA: Fetch Jobs", "AN: Fetch & Filter", "Remotive: Fetch & Filter",
        "AN Remote: Fetch & Filter", "Himalayas: Fetch & Filter",
    ]:
        conns = wf["connections"][crawler]["main"][0]
        merge_conn = next(c for c in conns if c["node"] == "Merge Sources")
        indexes.append(merge_conn["index"])
    assert sorted(indexes) == [0, 1, 2, 3, 4]


def test_unknown_crawler_id_fails_build():
    """Profile with an unknown crawler id should fail build with useful error."""
    # Use a temp profile copy with a bogus id
    import shutil, tempfile, os as _os
    with tempfile.TemporaryDirectory() as td:
        bad_profile = Path(td) / "profile_bad"
        shutil.copytree(REPO / "profiles" / "profile1", bad_profile)
        search = json.loads((bad_profile / "search.json").read_text(encoding="utf-8"))
        search["crawlers"] = ["does_not_exist"]
        (bad_profile / "search.json").write_text(json.dumps(search), encoding="utf-8")

        # Run with JOBS_FUNNEL_PROFILE pointing at our bad profile; we need to also
        # point the script at the parent dir. Easiest: monkey-patch via an env var
        # override is not supported. Instead, copy it under profiles/ temporarily.
        tmp_name = "profile_ci_bad_7f3a"
        tmp_dest = REPO / "profiles" / tmp_name
        shutil.copytree(bad_profile, tmp_dest)
        try:
            env = _os.environ.copy()
            env["JOBS_FUNNEL_PROFILE"] = tmp_name
            result = subprocess.run(
                [sys.executable, "scripts/build_workflow.py"],
                cwd=REPO, env=env, capture_output=True, text=True
            )
            assert result.returncode != 0
            combined = result.stdout + result.stderr
            assert "does_not_exist" in combined
        finally:
            shutil.rmtree(tmp_dest, ignore_errors=True)
