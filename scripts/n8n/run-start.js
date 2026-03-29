// Insert a pipeline_runs row at the start of a pipeline execution.
// Detects trigger type and returns an INSERT ... RETURNING query.
const profile = ($env.JOBS_FUNNEL_PROFILE || '').replace(/'/g, "''");
const executionId = $execution.id;

let triggerType = 'manual';
try { if ($('Cron Schedule').isExecuted) triggerType = 'cron'; } catch (e) { /* not triggered */ }
try { if ($('Run Analyze Only').isExecuted) triggerType = 'webhook'; } catch (e) { /* not triggered */ }

const query = `INSERT INTO pipeline_runs (execution_id, trigger_type, profile, status)
  VALUES ('${executionId}', '${triggerType}', '${profile}', 'running')
  RETURNING id, started_at`;

return [{ json: { _runStartQuery: query } }];
