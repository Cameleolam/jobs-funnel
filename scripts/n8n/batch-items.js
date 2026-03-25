// Batch all pending jobs into groups of 8, write each to a temp file
const fs = require('fs');
const BATCH_SIZE = 8;
const all = $input.all();
const tmpDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/') + '/temp';

// Ensure temp dir exists and clean old batch files
try { fs.mkdirSync(tmpDir, { recursive: true }); } catch (e) {}
try {
  const oldFiles = fs.readdirSync(tmpDir).filter(f => f.startsWith('n8n_batch_'));
  for (const f of oldFiles) { try { fs.unlinkSync(tmpDir + '/' + f); } catch (e) {} }
} catch (e) {}

const batches = [];
for (let i = 0; i < all.length; i += BATCH_SIZE) {
  const chunk = all.slice(i, i + BATCH_SIZE);
  const batchJobs = chunk.map(item => ({
    title: item.json.title || '',
    company: item.json.company || '',
    location: item.json.location || '',
    description: (item.json.description || '').substring(0, 3000),
    tags: item.json.tags || [],
    url: item.json.url || '',
    _likely_english: item.json.likely_english || false
  }));
  const tmpPath = tmpDir + '/n8n_batch_' + Date.now() + '_' + i + '.json';
  fs.writeFileSync(tmpPath, JSON.stringify(batchJobs), 'utf-8');
  const originals = chunk.map(item => ({
    id: item.json.id,
    url: item.json.url,
    title: item.json.title,
    company: item.json.company,
    location: item.json.location,
    source: item.json.source
  }));
  batches.push({ json: { _tmpPath: tmpPath, _batchOriginals: originals, _batchSize: chunk.length } });
}
return batches;
