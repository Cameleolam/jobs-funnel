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
    import shutil, os as _os

    tmp_dest = REPO / "profiles" / "profile_ci_bad_7f3a"
    shutil.rmtree(tmp_dest, ignore_errors=True)
    shutil.copytree(REPO / "profiles" / "profile1", tmp_dest)
    try:
        search = json.loads((tmp_dest / "search.json").read_text(encoding="utf-8"))
        search["crawlers"] = ["does_not_exist"]
        (tmp_dest / "search.json").write_text(json.dumps(search), encoding="utf-8")

        env = _os.environ.copy()
        env["JOBS_FUNNEL_PROFILE"] = tmp_dest.name
        result = subprocess.run(
            [sys.executable, "scripts/build_workflow.py"],
            cwd=REPO, env=env, capture_output=True, text=True
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "does_not_exist" in combined
    finally:
        shutil.rmtree(tmp_dest, ignore_errors=True)


def test_streaming_embed_nodes_replace_inline_embed_chain():
    wf = run_build("profile1")
    node_names = {n["name"] for n in wf["nodes"]}

    assert "Embed: Loop Control" in node_names
    assert "Embed More?" in node_names
    assert "Embed: Next Batch" in node_names
    assert "Embed: Metrics Update" in node_names

    assert "Embed: Prep Query" not in node_names
    assert "Embed: Fetch IDs" not in node_names
    assert "Embed: Execute" not in node_names
    assert "Embed: Collect Metrics" not in node_names


def test_streaming_embed_interleaves_before_each_pending_fetch():
    wf = run_build("profile1")
    conns = wf["connections"]

    db_fetch = next(n for n in wf["nodes"] if n["name"] == "DB: Fetch Pending")
    assert "embedding_calibration IS NOT NULL" in db_fetch["parameters"]["query"]

    loop_node = next(n for n in wf["nodes"] if n["name"] == "Embed: Loop Control")
    assert loop_node["parameters"]["mode"] == "runOnceForAllItems"
    assert "executeOnce" not in loop_node

    assert conns["Has Results?"]["main"][1][0]["node"] == "Start Analyze"
    assert conns["Has New?"]["main"][1][0]["node"] == "Start Analyze"
    assert conns["DB: Insert Jobs"]["main"][0][0]["node"] == "Start Analyze"
    assert conns["Start Analyze"]["main"][0][0]["node"] == "Rescore: Uncalibrated"
    assert conns["DB: Run Start (Analyze)"]["main"][0][0]["node"] == "Rescore: Uncalibrated"
    assert conns["Rescore: Uncalibrated"]["main"][0][0]["node"] == "Embed: Loop Control"
    assert conns["Embed: Loop Control"]["main"][0][0]["node"] == "Embed: Metrics Update"
    assert conns["Embed: Metrics Update"]["main"][0][0]["node"] == "Embed More?"

    embed_more_true = conns["Embed More?"]["main"][0][0]["node"]
    embed_more_false = conns["Embed More?"]["main"][1][0]["node"]
    assert embed_more_true == "Embed: Next Batch"
    assert embed_more_false == "DB: Fetch Pending"
    assert conns["Embed: Next Batch"]["main"][0][0]["node"] == "DB: Fetch Pending"
    assert conns["Check More Pending"]["main"][0][0]["node"] == "Embed: Loop Control"
