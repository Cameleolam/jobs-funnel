// Filter out URLs already in Postgres, cap at 80
let seenRows;
try { seenRows = $('Dedup: Get Seen URLs').all(); } catch (e) { seenRows = []; }
const seenUrls = new Set(seenRows.map(r => r.json.url).filter(Boolean));

const jobs = $('Has Results?').all().filter(item => {
  const url = item.json?.url;
  return url && !seenUrls.has(url);
});

return jobs.length > 0 ? jobs.slice(0, 80) : [];
