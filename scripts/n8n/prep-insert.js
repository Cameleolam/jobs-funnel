// Build safe INSERT query for each job
/* {{include:scripts/n8n/lib/sql.js}} */

const table = sqlIdentifier($env.JOBS_FUNNEL_TABLE);

const items = $input.all().filter(item => item.json.url && !item.json._empty);
if (items.length === 0) return [{ json: { _insertQuery: 'SELECT 1' } }];
return items.map(item => {
  const j = item.json;
  const postedAt = j.posted_at ? sqlStr(j.posted_at) : 'NULL';
  const descQuality = j.description_quality || 'unknown';
  const query = `INSERT INTO ${table} (url, title, company, location, description, description_quality, source, external_id, tags, remote, likely_english, staffing_agency, geo_mismatch, salary_min, salary_max, salary_currency, start_date, posted_at) VALUES (${sqlStr(j.url)}, ${sqlStr(j.title)}, ${sqlStr(j.company)}, ${sqlStr(j.location)}, ${sqlStr((j.description || '').substring(0, 20000))}, ${sqlStr(descQuality)}, ${sqlStr(j.source)}, ${sqlStr(j.external_id)}, ${jsonbLiteral(j.tags)}, ${sqlBool(j.remote)}, ${sqlBool(j.likely_english)}, ${sqlBool(j.staffing_agency)}, ${sqlBool(j.geo_mismatch)}, ${sqlInt(j.salary_min)}, ${sqlInt(j.salary_max)}, ${sqlStr(j.salary_currency || null)}, ${sqlStr(j.start_date || null)}, ${postedAt}) ON CONFLICT (url) DO NOTHING`;
  let combinedQuery = query;
  if (j._rawApiData) {
    const rawJson = JSON.stringify(j._rawApiData);
    combinedQuery += `; INSERT INTO job_raw_data (url, raw_json, source) VALUES (${sqlStr(j.url)}, ${dollarQuote(rawJson, 'rd')}::jsonb, ${sqlStr(j.source)}) ON CONFLICT (url) DO NOTHING`;
  }
  return { json: { _insertQuery: combinedQuery } };
});
