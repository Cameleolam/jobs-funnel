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

const items = $input.all().filter(item => item.json.url && !item.json._empty);
if (items.length === 0) return [{ json: { _insertQuery: 'SELECT 1' } }];
return items.map(item => {
  const j = item.json;
  const postedAt = j.posted_at ? sqlStr(j.posted_at) : 'NULL';
  const descQuality = j.description_quality || 'unknown';
  const query = `INSERT INTO ${table} (url, title, company, location, description, description_quality, source, external_id, tags, remote, likely_english, salary_min, salary_max, salary_currency, start_date, posted_at) VALUES (${sqlStr(j.url)}, ${sqlStr(j.title)}, ${sqlStr(j.company)}, ${sqlStr(j.location)}, ${sqlStr((j.description || '').substring(0, 20000))}, ${sqlStr(descQuality)}, ${sqlStr(j.source)}, ${sqlStr(j.external_id)}, ${jsonbLiteral(j.tags)}, ${j.remote || false}, ${j.likely_english || false}, ${j.salary_min || 'NULL'}, ${j.salary_max || 'NULL'}, ${sqlStr(j.salary_currency || null)}, ${sqlStr(j.start_date || null)}, ${postedAt}) ON CONFLICT (url) DO NOTHING`;
  let combinedQuery = query;
  if (j._rawApiData) {
    const rawJson = JSON.stringify(j._rawApiData);
    let tag = '$rd$';
    if (rawJson.includes(tag)) tag = '$rd2$';
    combinedQuery += `; INSERT INTO job_raw_data (url, raw_json, source) VALUES (${sqlStr(j.url)}, ${tag}${rawJson}${tag}::jsonb, ${sqlStr(j.source)}) ON CONFLICT (url) DO NOTHING`;
  }
  return { json: { _insertQuery: combinedQuery } };
});
