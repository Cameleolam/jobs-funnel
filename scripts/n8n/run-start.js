// Insert a pipeline_runs row at the start of a pipeline execution.
// Detects trigger type and returns an INSERT ... RETURNING query.
const profile = ($env.JOBS_FUNNEL_PROFILE || '').replace(/'/g, "''");
const executionId = $execution.id;

let triggerType = 'manual';
try { if ($('Cron Schedule').isExecuted) triggerType = 'cron'; } catch (e) { /* not triggered */ }
try { if ($('Run Analyze Only').isExecuted) triggerType = 'webhook'; } catch (e) { /* not triggered */ }

// Finalize any orphaned runs (interrupted pipelines left in 'running' state)
const cleanup = `UPDATE pipeline_runs
  SET status = 'interrupted', finished_at = NOW(),
      duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::int * 1000,
      notes = COALESCE(notes || '; ', '') || 'Auto-closed: still running when next pipeline started'
  WHERE status = 'running'`;

const insert = `INSERT INTO pipeline_runs (execution_id, trigger_type, profile, status)
  VALUES ('${executionId}', '${triggerType}', '${profile}', 'running')
  RETURNING id, started_at`;

const query = cleanup + ';\n' + insert;

return [{ json: { _runStartQuery: query } }];
