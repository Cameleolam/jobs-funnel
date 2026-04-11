// Filter out jobs already in Postgres — by URL or by normalized company+title
// Let this throw if upstream DB node failed — better than bypassing dedup
const seenRows = $('Dedup: Get Seen URLs').all();
const seenUrls = new Set(seenRows.map(r => r.json.url).filter(Boolean));

// Build a set of normalized company|title keys from existing DB rows
const seenKeys = new Set();
for (const r of seenRows) {
  const t = (r.json.title || '').toLowerCase().trim();
  const c = (r.json.company || '').toLowerCase().trim();
  if (t || c) seenKeys.add(c + '|' + t);
}

function normalizeKey(title, company) {
  return (company || '').toLowerCase().trim() + '|' + (title || '').toLowerCase().trim();
}

const jobs = $('Has Results?').all().filter(item => {
  const url = item.json?.url;
  if (!url || seenUrls.has(url)) return false;
  const key = normalizeKey(item.json.title, item.json.company);
  return !seenKeys.has(key);
});

if (jobs.length === 0) return [{ json: { _empty: true } }];
return jobs;
