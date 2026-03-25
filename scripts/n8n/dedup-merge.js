// Deduplicate merged results by normalized company+title
const all = $input.all().filter(i => i.json.url);
const seen = new Set();
const unique = [];

function normalize(s) {
  return (s || '')
    .toLowerCase()
    .trim()
    .replace(/\s+(gmbh|ag|se|kg|co|ltd|inc|ug|mbh|e\.v\.|ohg|gbr)\.?\s*$/i, '')
    .replace(/\s+/g, ' ')
    .replace(/[^\w\s]/g, '');
}

for (const item of all) {
  const job = item.json;
  const key = normalize(job.company) + '|' + normalize(job.title);
  if (!seen.has(key)) {
    seen.add(key);
    unique.push(job);
  }
}

if (unique.length === 0) return [];
return unique.map(j => ({ json: j }));
