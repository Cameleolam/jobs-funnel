// Build safe INSERT query for each job
const table = $env.JOBS_FUNNEL_TABLE;
// Proper SQL escaping: handles quotes, backslashes, null bytes
function sqlStr(s) {
  if (s === null || s === undefined) return 'NULL';
  return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "''").replace(/\0/g, '') + "'";
}

// Dollar-quoted JSONB literal: avoids double-encoding from sqlStr + ::jsonb cast
function jsonbLiteral(value) {
  const arr = Array.isArray(value) ? value : [];
  const json = JSON.stringify(arr);
  let tag = '$jb$';
  if (json.includes(tag)) tag = '$jb2$';
  return tag + json + tag + '::jsonb';
}

return $input.all().map(item => {
  const j = item.json;
  const postedAt = j.posted_at ? sqlStr(j.posted_at) : 'NULL';
  const query = `INSERT INTO ${table} (url, title, company, location, description, source, external_id, tags, remote, likely_english, salary_min, salary_max, salary_currency, start_date, posted_at) VALUES (${sqlStr(j.url)}, ${sqlStr(j.title)}, ${sqlStr(j.company)}, ${sqlStr(j.location)}, ${sqlStr((j.description || '').substring(0, 10000))}, ${sqlStr(j.source)}, ${sqlStr(j.external_id)}, ${jsonbLiteral(j.tags)}, ${j.remote || false}, ${j.likely_english || false}, ${j.salary_min || 'NULL'}, ${j.salary_max || 'NULL'}, ${sqlStr(j.salary_currency || null)}, ${sqlStr(j.start_date || null)}, ${postedAt}) ON CONFLICT (url) DO NOTHING`;
  return { json: { _insertQuery: query } };
});
