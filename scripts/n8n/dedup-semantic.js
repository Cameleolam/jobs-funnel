// Prep semantic duplicate detection: collect newly analyzed jobs + existing jobs,
// write a temp file for dedup_semantic.py to process.
const fs = require('fs');
const table = $env.JOBS_FUNNEL_TABLE;
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const tmpDir = projectDir + '/temp';

// Collect newly analyzed job IDs from the batch originals (via Parse + Prep Update)
// We reference the Batch Items node which has _batchOriginals with id/title/company/location
const batchItems = $('Batch Items').all();
const parseResults = $('Parse + Prep Update').all();

const newJobs = [];
for (let b = 0; b < batchItems.length; b++) {
  const originals = (batchItems[b].json._batchOriginals) || [];
  const updateQuery = (parseResults[b] && parseResults[b].json._updateQuery) || '';
  for (let i = 0; i < originals.length; i++) {
    // Only include successfully analyzed jobs (query contains status = 'analyzed')
    if (updateQuery.includes("status = 'analyzed'")) {
      newJobs.push({
        id: originals[i].id,
        title: originals[i].title || '',
        company: originals[i].company || '',
        location: originals[i].location || '',
      });
    }
  }
}

if (newJobs.length === 0) {
  return [{ json: { _dedupSkipped: true, _dedupQuery: '' } }];
}

// Get existing jobs from the preceding Postgres fetch node
const existingRows = $('Dedup: Fetch Recent').all();
const existingJobs = existingRows
  .filter(r => r.json.id != null)
  .map(r => ({
    id: r.json.id,
    title: r.json.title || '',
    company: r.json.company || '',
    location: r.json.location || '',
  }));

if (existingJobs.length === 0) {
  return [{ json: { _dedupSkipped: true, _dedupQuery: '' } }];
}

// Filter out existing jobs that are in the new batch (no self-comparison)
const newIds = new Set(newJobs.map(j => j.id));
const filteredExisting = existingJobs.filter(j => !newIds.has(j.id));

if (filteredExisting.length === 0) {
  return [{ json: { _dedupSkipped: true, _dedupQuery: '' } }];
}

// Write temp file for dedup_semantic.py
fs.mkdirSync(tmpDir, { recursive: true });
const tmpPath = tmpDir + '/n8n_dedup_' + Date.now() + '.json';
fs.writeFileSync(tmpPath, JSON.stringify({
  new_jobs: newJobs,
  existing_jobs: filteredExisting,
}), 'utf-8');

return [{ json: { _dedupTmpPath: tmpPath } }];
