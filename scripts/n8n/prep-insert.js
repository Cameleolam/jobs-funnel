// Build safe INSERT query for each job
// Proper SQL escaping: handles quotes, backslashes, null bytes
function sqlStr(s) {
  if (s === null || s === undefined) return 'NULL';
  return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "''").replace(/\0/g, '') + "'";
}

return $input.all().map(item => {
  const j = item.json;
  const query = `INSERT INTO jobs (url, title, company, location, description, source, external_id, tags, remote, likely_english) VALUES (${sqlStr(j.url)}, ${sqlStr(j.title)}, ${sqlStr(j.company)}, ${sqlStr(j.location)}, ${sqlStr((j.description || '').substring(0, 10000))}, ${sqlStr(j.source)}, ${sqlStr(j.external_id)}, ${sqlStr(JSON.stringify(j.tags || []))}::jsonb, ${j.remote || false}, ${j.likely_english || false}) ON CONFLICT (url) DO NOTHING`;
  return { json: { _insertQuery: query } };
});
