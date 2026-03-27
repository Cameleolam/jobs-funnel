// Filter out URLs already in Postgres, cap at configurable limit
const config = JSON.parse(require('fs').readFileSync(
  ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/') + '/config.json', 'utf-8'
));
const CAP = config.dedup_cap || 80;
// Let this throw if upstream DB node failed — better than bypassing dedup
const seenRows = $('Dedup: Get Seen URLs').all();
const seenUrls = new Set(seenRows.map(r => r.json.url).filter(Boolean));

const jobs = $('Has Results?').all().filter(item => {
  const url = item.json?.url;
  return url && !seenUrls.has(url);
});

if (jobs.length === 0) return [];
const capped = jobs.slice(0, CAP);
if (jobs.length > CAP && capped.length > 0) {
  capped[0].json._truncated = true;
  capped[0].json._droppedCount = jobs.length - CAP;
}
return capped;
