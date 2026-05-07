// Run with: node tests/scripts/test_embed_next_batch_js.js
const fs = require('fs');
const vm = require('vm');

let failed = 0;
function assert(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    failed++;
  }
}

function runCase({config, priorStdout, staticData, runId}) {
  const code = fs.readFileSync('scripts/n8n/embed-next-batch.js', 'utf-8');
  const context = {
    require: (name) => {
      if (name === 'fs') {
        return {
          readFileSync: () => JSON.stringify(config || {}),
        };
      }
      throw new Error('unexpected require ' + name);
    },
    $env: {JOBS_FUNNEL_PROJECT_DIR: 'D:/projects/jobs_funnel'},
    $input: {all: () => [{json: {_trigger: 'check_more'}}]},
    $execution: {id: 'exec-1'},
    $getWorkflowStaticData: () => staticData,
    $: (name) => {
      if (name === 'Embed: Next Batch') {
        return {
          last: () => ({json: {stdout: priorStdout || ''}}),
        };
      }
      if (name === 'DB: Run Start') {
        return {
          first: () => ({json: {id: runId || 101}}),
        };
      }
      throw new Error('node not available: ' + name);
    },
  };
  return vm.runInNewContext('(function(){' + code + '\n})()', context);
}

{
  const staticData = {};
  const out = runCase({
    config: {embed_batch_size: 8, embed_cap_per_run: 80},
    staticData,
    runId: 12,
  })[0].json;
  assert(out._embedMoreToDo === true, 'first iteration asks for embed');
  assert(out._embedLimit === 8, 'first iteration limit');
  assert(out._embedCapRemaining === 80, 'first iteration cap remaining');
  assert(out._embedMetricsQuery.includes('embed_count = 0'), 'first metrics count zero');
}

{
  const staticData = {};
  const prior = JSON.stringify({
    batch_id: 'batch-a',
    processed: 8,
    failed: 1,
    attempted: 9,
    has_more: true,
  });
  const out = runCase({
    config: {embed_batch_size: 8, embed_cap_per_run: 10},
    priorStdout: prior,
    staticData,
    runId: 13,
  })[0].json;
  assert(out._embedMoreToDo === true, 'remaining cap still embeds');
  assert(out._embedLimit === 1, 'limit clamps to remaining cap');
  assert(out._embedCapRemaining === 1, 'cap remaining after prior batch');
  assert(out._embedMetricsQuery.includes('embed_count = 8'), 'processed metric');
  assert(out._embedMetricsQuery.includes('embed_failures = 1'), 'failed metric');
}

{
  const staticData = {};
  const prior = JSON.stringify({
    batch_id: 'batch-b',
    processed: 8,
    failed: 0,
    attempted: 8,
    has_more: true,
  });
  runCase({config: {embed_batch_size: 8, embed_cap_per_run: 80}, priorStdout: prior, staticData, runId: 14});
  runCase({config: {embed_batch_size: 8, embed_cap_per_run: 80}, priorStdout: prior, staticData, runId: 14});
  assert(staticData.embedRunTotals['14'].processed === 8, 'same batch_id counted once');
}

{
  const staticData = {};
  const out = runCase({
    config: {embed_batch_size: 8, embed_cap_per_run: 8},
    priorStdout: JSON.stringify({batch_id: 'batch-c', processed: 8, failed: 0, attempted: 8, has_more: true}),
    staticData,
    runId: 15,
  })[0].json;
  assert(out._embedMoreToDo === false, 'cap hit stops embedding');
  assert(out._embedMetricsQuery.includes('embed_degraded = TRUE'), 'cap hit degrades metrics');
}

{
  const staticData = {};
  runCase({config: {embed_batch_size: 8, embed_cap_per_run: 80}, priorStdout: 'not-json', staticData, runId: 16});
  runCase({config: {embed_batch_size: 8, embed_cap_per_run: 80}, priorStdout: 'still-not-json', staticData, runId: 16});
  const out = runCase({config: {embed_batch_size: 8, embed_cap_per_run: 80}, priorStdout: 'bad-json-again', staticData, runId: 16})[0].json;
  assert(out._embedMoreToDo === false, 'three empty/error summaries stop embedding');
  assert(out._embedMetricsQuery.includes('embed_degraded = TRUE'), 'empty streak degrades metrics');
}

if (failed > 0) {
  console.error(`${failed} test(s) failed`);
  process.exit(1);
}
console.log('All embed-next-batch JS tests passed');
