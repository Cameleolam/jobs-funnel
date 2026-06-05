// Batch all pending jobs into groups of N, write each to a temp file
const fs = require('fs');
const config = JSON.parse(fs.readFileSync(
  ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/') + '/config.json', 'utf-8'
));
const BATCH_SIZE = config.batch_size || 8;
const all = $input.all();
const tmpDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/') + '/temp';

// Ensure temp dir exists (let it throw if it can't create)
fs.mkdirSync(tmpDir, { recursive: true });
// Clean old batch files (non-critical, silent on failure)
try {
  const oldFiles = fs.readdirSync(tmpDir).filter(f => f.startsWith('n8n_batch_'));
  for (const f of oldFiles) { try { fs.unlinkSync(tmpDir + '/' + f); } catch (e) {} }
} catch (e) {}

const batches = [];
for (let i = 0; i < all.length; i += BATCH_SIZE) {
  const chunk = all.slice(i, i + BATCH_SIZE);
  const batchJobs = chunk.map(item => {
    const j = item.json || {};
    return {
      job: {
        title: j.title || '',
        company: j.company || '',
        location: j.location || '',
        url: j.url || '',
        source: j.source || '',
        external_id: j.external_id || '',
        tags: j.tags || [],
        salary_min: j.salary_min || null,
        salary_max: j.salary_max || null,
        salary_currency: j.salary_currency || null,
        employment_type: j.employment_type || null,
        seniority_level: j.seniority_level || null,
        start_date: j.start_date || null,
        posted_at: j.posted_at || null
      },
      content: {
        description: j.description || '',
        description_quality: j.description_quality || 'unknown'
      },
      signals: {
        remote: j.remote || false,
        likely_english: j.likely_english || false,
        staffing_agency: j.staffing_agency || false,
        geo_mismatch: j.geo_mismatch || false,
        embedding_calibration_present: j.embedding_calibration != null
      },
      source_context: {
        source: j.source || '',
        url: j.url || '',
        description_quality: j.description_quality || 'unknown',
        application_channel: null,
        postulability: null
      }
    };
  });
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
