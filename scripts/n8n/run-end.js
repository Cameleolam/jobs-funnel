// Finalize the pipeline_runs row with stats and duration.
// Reads run_id from whichever DB: Run Start node executed.
const table = ($env.JOBS_FUNNEL_TABLE || 'jobs').replace(/'/g, "''");

let runId = null;
let startedAt = null;
try {
  const row = $('DB: Run Start').first().json;
  runId = row.id;
  startedAt = row.started_at;
} catch (e) { /* full pipeline path not taken */ }
if (!runId) {
  try {
    const row = $('DB: Run Start (Analyze)').first().json;
    runId = row.id;
    startedAt = row.started_at;
  } catch (e) { /* neither path?? */ }
}

if (!runId) {
  // No run was started — skip gracefully
  return [{ json: { _runEndQuery: 'SELECT 1' } }];
}

const durationMs = Date.now() - new Date(startedAt).getTime();

// Crawl stats from the Start Analyze node (0 for webhook/analyze-only path)
let crawled = 0;
let inserted = 0;
try {
  const sa = $('Start Analyze').first().json;
  crawled = sa._crawled || 0;
  inserted = sa._inserted || 0;
} catch (e) { /* analyze-only path — no crawl */ }

// Escape the started_at timestamp for SQL
const safeStarted = new Date(startedAt).toISOString();

const query = `
  WITH stats AS (
    SELECT
      COUNT(*) FILTER (WHERE analyzed_at >= '${safeStarted}') AS analyzed,
      COUNT(*) FILTER (WHERE error_code IS NOT NULL AND (analyzed_at >= '${safeStarted}' OR (status IN ('error','dead') AND crawled_at >= '${safeStarted}'))) AS errored
    FROM ${table}
  )
  UPDATE pipeline_runs SET
    finished_at = NOW(),
    jobs_crawled = ${crawled},
    jobs_inserted = ${inserted},
    jobs_analyzed = stats.analyzed,
    jobs_errored = stats.errored,
    duration_ms = ${durationMs},
    status = CASE WHEN stats.errored > 0 THEN 'partial' ELSE 'success' END
  FROM stats
  WHERE pipeline_runs.id = ${runId}`;

return [{ json: { _runEndQuery: query } }];
