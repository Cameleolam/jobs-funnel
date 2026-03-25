// Format Postgres rows into Google Sheet columns, skip if no unsynced rows
const all = $input.all().filter(item => item.json.id != null);
if (all.length === 0) return [];

return all.map(item => {
  const j = item.json;
  const crawledAt = j.crawled_at ? new Date(j.crawled_at) : new Date();
  const blockers = Array.isArray(j.hard_blockers) ? j.hard_blockers.join('; ') : (j.hard_blockers || '');
  const matches = Array.isArray(j.strong_matches) ? j.strong_matches.join('; ') : (j.strong_matches || '');
  const decision = j.decision || 'SKIP';

  return { json: {
    'Date': crawledAt.toISOString().slice(0, 10),
    'Fetched At': crawledAt.toISOString().replace('T', ' ').slice(0, 19) + ' UTC',
    'Source': j.source || '',
    'Company': j.company || '',
    'Role': j.title || '',
    'Location': j.location || '',
    'Score': j.fit_score || 0,
    'Decision': decision,
    'CV Variant': j.cv_variant || 'software',
    'Blockers': blockers,
    'Strong Matches': matches,
    'Reasoning': j.reasoning || '',
    'Status': decision === 'SKIP' ? 'skipped' : 'review',
    'Drive Link': '',
    'Job URL': j.url || '',
    'Notes': j.priority_notes || '',
    _dbId: j.id
  }};
});
