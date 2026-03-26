// Format Postgres rows into Google Sheet columns, skip if no unsynced rows
const all = $input.all().filter(item => item.json.id != null);
if (all.length === 0) return [];

return all.map(item => {
  const j = item.json;
  const crawledAt = j.crawled_at ? new Date(j.crawled_at) : new Date();
  const blockers = Array.isArray(j.hard_blockers) ? j.hard_blockers.join('; ') : (j.hard_blockers || '');
  const matches = Array.isArray(j.strong_matches) ? j.strong_matches.join('; ') : (j.strong_matches || '');
  const decision = j.decision || 'SKIP';

  // Status reflects user action, not auto-classification
  let status = j.user_status || '';
  if (!status && decision === 'SKIP') status = 'skipped';

  return { json: {
    'Date': crawledAt.toISOString().slice(0, 10),
    'Fetched At': crawledAt.toISOString().replace('T', ' ').slice(0, 19) + ' UTC',
    'Source': j.source || '',
    'Company': j.company || '',
    'Role': j.title || '',
    'Location': j.location || '',
    'Salary': j.salary_min && j.salary_max
      ? `${j.salary_min}-${j.salary_max} ${j.salary_currency || 'EUR'}`
      : (j.salary_min ? `${j.salary_min}+ ${j.salary_currency || 'EUR'}` : ''),
    'Score': j.fit_score || 0,
    'Decision': decision,
    'CV Variant': j.cv_variant || 'software',
    'Blockers': blockers,
    'Strong Matches': matches,
    'Reasoning': j.reasoning || '',
    'Status': status,
    'Drive Link': '',
    'Job URL': j.url || '',
    'Notes': j.priority_notes || '',
    'My Notes': j.notes || '',
    '_dbId': j.id
  }};
});
