// Filter out URLs already in Postgres — insert all new jobs, analyze phase handles batching
// Let this throw if upstream DB node failed — better than bypassing dedup
const seenRows = $('Dedup: Get Seen URLs').all();
const seenUrls = new Set(seenRows.map(r => r.json.url).filter(Boolean));

const jobs = $('Has Results?').all().filter(item => {
  const url = item.json?.url;
  return url && !seenUrls.has(url);
});

if (jobs.length === 0) return [];
return jobs;
