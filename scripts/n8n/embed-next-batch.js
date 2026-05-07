const fs = require('fs');

function readConfig() {
  const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
  try {
    return JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
  } catch (e) {
    return {};
  }
}

function parseSummary(stdout) {
  const text = String(stdout || '').trim();
  if (!text) {
    return {parsed: false, summary: {processed: 0, failed: 0, attempted: 0, has_more: true}};
  }
  try {
    const summary = JSON.parse(text.split('\n').pop());
    return {
      parsed: true,
      summary: {
        batch_id: summary.batch_id || '',
        processed: Number(summary.processed || 0),
        failed: Number(summary.failed || 0),
        attempted: Number(summary.attempted || ((summary.processed || 0) + (summary.failed || 0))),
        has_more: summary.has_more !== false,
      },
    };
  } catch (e) {
    return {parsed: false, summary: {processed: 0, failed: 0, attempted: 0, has_more: true}};
  }
}

function readRunStart() {
  try {
    return $('DB: Run Start').first().json;
  } catch (e) {}
  try {
    return $('DB: Run Start (Analyze)').first().json;
  } catch (e) {}
  return {};
}

const config = readConfig();
const batchSize = Number(config.embed_batch_size || 8);
const configuredCap = Number(config.embed_cap_per_run == null ? 80 : config.embed_cap_per_run);
const cap = configuredCap > 0 ? configuredCap : Number.POSITIVE_INFINITY;

let priorStdout = '';
try {
  priorStdout = $('Embed: Next Batch').last().json.stdout || '';
} catch (e) {}

const parsed = parseSummary(priorStdout);
const summary = parsed.summary;
const runStart = readRunStart();
const runId = runStart.id || $execution.id || 'unknown';
const staticData = $getWorkflowStaticData('global');
staticData.embedRunTotals = staticData.embedRunTotals || {};
const totals = staticData.embedRunTotals[String(runId)] || {
  processed: 0,
  failed: 0,
  attempted: 0,
  lastBatchId: '',
  emptyStreak: 0,
};

if (parsed.parsed && summary.batch_id && summary.batch_id !== totals.lastBatchId) {
  totals.processed += summary.processed;
  totals.failed += summary.failed;
  totals.attempted += summary.attempted;
  totals.lastBatchId = summary.batch_id;
  totals.emptyStreak = summary.attempted === 0 ? totals.emptyStreak + 1 : 0;
} else if (!parsed.parsed && priorStdout) {
  totals.emptyStreak += 1;
}

const capRemaining = Number.isFinite(cap) ? Math.max(0, cap - totals.attempted) : -1;
const capHit = Number.isFinite(cap) && capRemaining === 0 && summary.has_more;
const stalled = totals.emptyStreak >= 3;
const moreToEmbed = summary.has_more && !capHit && !stalled;
const degraded = totals.failed > 0 || capHit || stalled;

staticData.embedRunTotals[String(runId)] = totals;

let metricsQuery = 'SELECT 1';
if (runStart.id) {
  metricsQuery =
    'UPDATE pipeline_runs SET ' +
    `embed_count = ${totals.processed}, ` +
    `embed_failures = ${totals.failed}, ` +
    `embed_degraded = ${degraded ? 'TRUE' : 'FALSE'} ` +
    `WHERE id = ${Number(runStart.id)}`;
}

return [{
  json: {
    _embedLimit: capRemaining < 0 ? batchSize : Math.min(batchSize, capRemaining),
    _embedCapRemaining: capRemaining,
    _embedMoreToDo: moreToEmbed,
    _embedMetricsQuery: metricsQuery,
    _embedSummary: {
      last: summary,
      cumulative: totals,
      capRemaining,
      capHit,
      stalled,
      degraded,
    },
  },
}];
