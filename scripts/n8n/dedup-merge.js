// Deduplicate merged results by company+title
const all = $input.all().filter(i => i.json.url);
const seen = new Set();
const unique = [];

for (const item of all) {
  const job = item.json;
  const key = ((job.company || '') + '|' + (job.title || '')).toLowerCase().trim();
  if (!seen.has(key)) {
    seen.add(key);
    unique.push(job);
  }
}

if (unique.length === 0) return [];
return unique.map(j => ({ json: j }));
