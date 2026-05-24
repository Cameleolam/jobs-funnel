/* {{include:scripts/n8n/lib/sql.js}} */

const table = sqlIdentifier($env.JOBS_FUNNEL_TABLE);

function readRunStart() {
  try { return $('DB: Run Start').first().json; } catch (e) {}
  try { return $('DB: Run Start (Analyze)').first().json; } catch (e) {}
  return {};
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function metricCount(value) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

const stdout = ($input.first().json.stdout || '').trim();
if (!stdout) return [{ json: { _dedupQuery: 'SELECT 1' } }];

let payload;
try {
  payload = JSON.parse(stdout);
} catch (e) {
  payload = null;
}

let pairs = [];
let metrics = {};
if (Array.isArray(payload)) {
  pairs = payload;
} else if (isPlainObject(payload)) {
  pairs = Array.isArray(payload.pairs) ? payload.pairs : [];
  metrics = isPlainObject(payload.metrics) ? payload.metrics : {};
}
const out = [];

for (const p of pairs) {
  if (!isPlainObject(p)) continue;
  const newId = Number(p.new_id);
  const existingId = Number(p.existing_id);
  if (Number.isFinite(newId) && Number.isFinite(existingId)) {
    out.push({
      json: {
        _dedupQuery: `UPDATE ${table} SET possible_duplicate_of = ${existingId}, duplicate_confirmed = TRUE WHERE id = ${newId} AND possible_duplicate_of IS NULL`
      }
    });
  }
}

const runStart = readRunStart();
if (runStart.id) {
  out.push({
    json: {
      _dedupQuery:
        `UPDATE pipeline_runs SET ` +
        `dedup_vector_resolved = dedup_vector_resolved + ${metricCount(metrics.vector_resolved)}, ` +
        `dedup_claude_calls = dedup_claude_calls + ${metricCount(metrics.claude_calls)} ` +
        `WHERE id = ${Number(runStart.id)}`
    }
  });
}

return out.length ? out : [{ json: { _dedupQuery: 'SELECT 1' } }];
