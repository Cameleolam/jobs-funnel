// Collect ExecuteCommand outputs from the embed step, build pipeline_runs
// metric update query.
const items = $input.all();
let okCount = 0;
let failCount = 0;
let degraded = false;

for (const it of items) {
  const stdout = (it.json && it.json.stdout) || '';
  try {
    const payload = JSON.parse(stdout.trim().split('\n').pop() || '{}');
    if (payload.status === 'ok') okCount++;
    else if (payload.status === 'embed_failed') { failCount++; degraded = true; }
    else if (payload.status === 'error') { failCount++; degraded = true; }
  } catch (e) {
    failCount++;
    degraded = true;
  }
}

// Lookup runId from whichever DB: Run Start variant ran (matches run-end.js pattern)
let runId = null;
try { runId = $('DB: Run Start').first().json.id; } catch (e) {}
if (!runId) {
  try { runId = $('DB: Run Start (Analyze)').first().json.id; } catch (e) {}
}

if (runId) {
  const updates = [];
  updates.push(`embed_count = COALESCE(embed_count,0) + ${okCount}`);
  updates.push(`embed_failures = COALESCE(embed_failures,0) + ${failCount}`);
  if (degraded) updates.push(`embed_degraded = TRUE`);
  const sql = `UPDATE pipeline_runs SET ${updates.join(', ')} WHERE id = ${Number(runId)}`;
  return [{ json: { _embedMetricsQuery: sql, _embedSummary: { ok: okCount, fail: failCount, degraded } } }];
}
return [{ json: { _embedMetricsQuery: 'SELECT 1', _embedSummary: { ok: okCount, fail: failCount, degraded } } }];
