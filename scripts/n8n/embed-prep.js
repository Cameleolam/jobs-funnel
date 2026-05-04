// Prep step: read inserted job ids from the DB Insert step's RETURNING output.
//
// Strategy: re-query the DB for just-inserted ids using a small SELECT
// keyed on the URLs we just inserted. This avoids depending on n8n's
// per-driver behaviour around RETURNING in batched INSERTs.
const table = $env.JOBS_FUNNEL_TABLE;

const upstreamItems = $('Prep Insert').all();
const urls = upstreamItems
  .map(i => i.json && i.json._insertQuery)
  .filter(Boolean)
  .map(q => {
    const m = q.match(/INSERT INTO [^(]+\([^)]+\) VALUES \('([^']+(?:''[^']*)*)'/);
    return m ? m[1].replace(/''/g, "'") : null;
  })
  .filter(Boolean);

if (urls.length === 0) {
  return [{ json: { _embedQuery: 'SELECT 1 WHERE FALSE', _empty: true } }];
}

// Build a SELECT to fetch ids of rows that need embedding (just inserted OR
// already in DB without embeddings — covers idempotent re-runs).
const inClause = urls.map(u => "'" + u.replace(/'/g, "''") + "'").join(', ');
const query = `SELECT id FROM ${table} WHERE url IN (${inClause}) AND embedding IS NULL`;

return [{ json: { _embedQuery: query } }];
