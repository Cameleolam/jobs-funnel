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


def dedup_parse_code(wf):
    parse = next(n for n in wf["nodes"] if n["name"] == "Dedup: Parse Results")
    return parse["parameters"]["jsCode"]


def run_dedup_parse(code: str, stdout: str, run_start_id=17):
    harness = """
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const fn = new Function('$input', '$env', '$', input.code);
const $input = {
  first() {
    return { json: { stdout: input.stdout } };
  }
};
const $env = { JOBS_FUNNEL_TABLE: 'jobs' };
function $(name) {
  if (!input.runStartId) throw new Error(`missing ${name}`);
  return {
    first() {
      return { json: { id: input.runStartId } };
    }
  };
}
Promise.resolve(fn($input, $env, $)).then(
  result => process.stdout.write(JSON.stringify(result)),
  error => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  }
);
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"code": code, "stdout": stdout, "runStartId": run_start_id}),
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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
    import os as _os

    tmp_dest = REPO / "profiles" / "profile_ci_bad_minimal_7f3a"
    tmp_dest.mkdir(exist_ok=True)
    try:
        (tmp_dest / "search.json").write_text(
            json.dumps({"crawlers": ["does_not_exist"]}),
            encoding="utf-8",
        )

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
        try:
            (tmp_dest / "search.json").unlink()
            tmp_dest.rmdir()
        except OSError:
            pass


def test_streaming_embed_nodes_replace_inline_embed_chain():
    wf = run_build("profile1")
    node_names = {n["name"] for n in wf["nodes"]}

    assert "Embed: Loop Control" in node_names
    assert "Embed More?" in node_names
    assert "Embed: Next Batch" in node_names
    assert "Embed: Metrics Update" in node_names

    removed_inline_nodes = {
        "Embed: Prep " + "Query",
        "Embed: Fetch " + "IDs",
        "Embed: " + "Execute",
        "Embed: Collect " + "Metrics",
    }
    assert node_names.isdisjoint(removed_inline_nodes)


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


def test_streaming_embed_uses_loop_control_values_after_metrics_update():
    wf = run_build("profile1")

    embed_more = next(n for n in wf["nodes"] if n["name"] == "Embed More?")
    condition = embed_more["parameters"]["conditions"]["conditions"][0]
    assert "$(\"Embed: Loop Control\").first().json._embedMoreToDo" in condition["leftValue"]

    next_batch = next(n for n in wf["nodes"] if n["name"] == "Embed: Next Batch")
    command = next_batch["parameters"]["command"]
    assert "$(\"Embed: Loop Control\").first().json._embedLimit" in command
    assert "$(\"Embed: Loop Control\").first().json._embedCapRemaining" in command
    assert "$json._embedLimit" not in command
    assert "$json._embedCapRemaining" not in command


def test_phase2_dedup_uses_tiered_wrapper_and_metrics():
    wf = run_build("profile1")
    dedup_cmd = next(n for n in wf["nodes"] if n["name"] == "Dedup: Claude")
    command = dedup_cmd["parameters"]["command"]
    assert "scripts/run_dedup.py" in command
    assert "scripts/dedup_semantic.py" not in command

    code = dedup_parse_code(wf)
    assert "payload.pairs" in code
    assert "dedup_vector_resolved" in code
    assert "dedup_claude_calls" in code


def test_phase2_dedup_fetch_recent_uses_configured_scope_days():
    wf = run_build("profile1")
    fetch_recent = next(n for n in wf["nodes"] if n["name"] == "Dedup: Fetch Recent")
    query = fetch_recent["parameters"]["query"]

    assert "DEDUP_SCOPE_DAYS" in query
    assert "make_interval(days =>" in query
    assert "INTERVAL '30 days'" not in query


def test_phase2_dedup_prep_comments_reference_current_wrapper():
    wf = run_build("profile1")
    prep = next(n for n in wf["nodes"] if n["name"] == "Dedup: Semantic Prep")
    code = prep["parameters"]["jsCode"]

    assert "run_dedup.py" in code
    assert "dedup_semantic.py" not in code


def test_fresh_setup_schema_includes_pipeline_metric_columns():
    sql = (REPO / "scripts" / "setup_db.sql").read_text(encoding="utf-8")

    for column in [
        "embed_count",
        "embed_failures",
        "embed_degraded",
        "dedup_vector_resolved",
        "dedup_claude_calls",
        "score_critique_count",
        "score_human_flagged",
        "score_uncalibrated",
        "score_rescored",
    ]:
        assert column in sql


def test_phase2_dedup_parse_empty_stdout_returns_select_one_before_metrics():
    wf = run_build("profile1")
    code = dedup_parse_code(wf)

    assert "const stdout = ($input.first().json.stdout || '').trim();" in code
    assert "if (!stdout) return [{ json: { _dedupQuery: 'SELECT 1' } }];" in code
    assert code.index("if (!stdout)") < code.index("const runStart = readRunStart();")

    assert run_dedup_parse(code, "") == [{"json": {"_dedupQuery": "SELECT 1"}}]


def test_phase2_dedup_parse_executes_tiered_payloads_safely():
    wf = run_build("profile1")
    code = dedup_parse_code(wf)

    zero_pair_metrics = run_dedup_parse(
        code,
        json.dumps({"pairs": [], "metrics": {"vector_resolved": 3, "claude_calls": 2}}),
    )
    assert len(zero_pair_metrics) == 1
    assert "dedup_vector_resolved = dedup_vector_resolved + 3" in zero_pair_metrics[0]["json"]["_dedupQuery"]
    assert "dedup_claude_calls = dedup_claude_calls + 2" in zero_pair_metrics[0]["json"]["_dedupQuery"]

    legacy_array = run_dedup_parse(
        code,
        json.dumps([{"new_id": 22, "existing_id": 11}]),
        run_start_id=None,
    )
    assert legacy_array == [{
        "json": {
            "_dedupQuery": (
                "UPDATE jobs SET possible_duplicate_of = 11, duplicate_confirmed = TRUE "
                "WHERE id = 22 AND possible_duplicate_of IS NULL"
            )
        }
    }]

    assert run_dedup_parse(code, "{", run_start_id=None) == [{"json": {"_dedupQuery": "SELECT 1"}}]
    assert run_dedup_parse(code, "null", run_start_id=None) == [{"json": {"_dedupQuery": "SELECT 1"}}]
    assert run_dedup_parse(code, json.dumps({"pairs": {}}), run_start_id=None) == [
        {"json": {"_dedupQuery": "SELECT 1"}}
    ]

    sanitized_metrics = run_dedup_parse(
        code,
        json.dumps({
            "pairs": "bad",
            "metrics": {"vector_resolved": "many", "claude_calls": -4},
        }),
    )
    query = sanitized_metrics[0]["json"]["_dedupQuery"]
    assert "NaN" not in query
    assert "+ -" not in query
    assert "dedup_vector_resolved = dedup_vector_resolved + 0" in query
    assert "dedup_claude_calls = dedup_claude_calls + 0" in query
