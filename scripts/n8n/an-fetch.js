// Arbeitnow: paginate up to 10 pages, relaxed client-side filters
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = JSON.parse(fs.readFileSync(profileDir + '/search.json', 'utf-8'));

const MAX_PAGES = config.an_max_pages || 10;
const DELAY_MS = config.an_delay_ms || 5000;
const MAX_RETRIES = config.api_max_retries || 2;
const RETRY_DELAY = config.api_retry_delay_ms || 1000;
const cutoff = Date.now() - (config.an_days_back || 30) * 24 * 60 * 60 * 1000;

const STAFFING_PATTERNS = config.staffing_agency_patterns || [];
const GEO_ALLOWLIST = config.geo_allowlist || [];
function detectStaffingAgency(company) {
  if (!company) return false;
  const lower = String(company).toLowerCase();
  return STAFFING_PATTERNS.some(p => lower.includes(String(p).toLowerCase()));
}
function detectGeoMismatch(location, remote) {
  if (remote) return false;
  if (!location) return true;
  const lower = String(location).toLowerCase();
  return !GEO_ALLOWLIST.some(a => lower.includes(String(a).toLowerCase()));
}

// Retry with exponential backoff; skip retries for 4xx (permanent errors)
async function fetchWithRetry(opts) {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await this.helpers.httpRequest(opts);
    } catch (e) {
      const msg = e.message || String(e);
      const is4xx = /\b4\d{2}\b/.test(msg) || msg.includes('Bad Request') || msg.includes('Not Found');
      if (is4xx || attempt === MAX_RETRIES) throw e;
      await new Promise(r => setTimeout(r, RETRY_DELAY * Math.pow(2, attempt)));
    }
  }
}

const titleKw = search.an_title_keywords || [];
const tagKw = search.an_tag_keywords || [];
const locKw = search.an_location_keywords || [];
const negKw = search.an_negative_keywords || [];
const engWords = ['the','and','you','we','team','experience','requirements','about','our','will','work','join','role','position'];

function isLikelyEnglish(desc) {
  const sample = (desc || '').substring(0, 500).toLowerCase();
  const hits = engWords.filter(w => sample.includes(w)).length;
  return hits >= 3;
}

const allJobs = [];
const seen = new Set();
const errors = [];
var lastPage = 0;
const CB_THRESHOLD = config.circuit_breaker_threshold ?? 0.8;
const CB_MIN = config.circuit_breaker_min_requests ?? 5;
let totalRequests = 0;
let failedRequests = 0;
let circuitBroken = false;

for (let page = 1; page <= MAX_PAGES; page++) {
  if (page > 1) await new Promise(r => setTimeout(r, DELAY_MS));
  if (totalRequests >= CB_MIN && failedRequests / totalRequests >= CB_THRESHOLD) {
    circuitBroken = true;
    break;
  }
  lastPage = page;
  let body;
  try {
    body = await fetchWithRetry.call(this, { method: 'GET', url: `https://www.arbeitnow.com/api/job-board-api?page=${page}`, json: true });
    totalRequests++;
  } catch (e) {
    totalRequests++;
    failedRequests++;
    errors.push({ page, error: e.message || String(e) });
    continue; // Try next page instead of breaking
  }
  const data = body.data || [];
  if (data.length === 0) break;

  let allOld = true;
  for (const job of data) {
    const created = new Date(job.created_at * 1000 || job.created_at).getTime();
    if (created > cutoff) allOld = false;

    const t = (job.title || '').toLowerCase();
    const l = (job.location || '').toLowerCase();
    const tags = (job.tags || []).map(t => t.toLowerCase());
    const titleMatch = titleKw.some(k => t.includes(k));
    const tagMatch = tagKw.some(k => tags.includes(k));
    const locMatch = locKw.some(k => l.includes(k)) || job.remote;
    const negMatch = negKw.some(k => t.includes(k));

    if (!negMatch && (titleMatch || tagMatch || locMatch) && created > cutoff) {
      const key = job.slug || job.url || job.title;
      if (!seen.has(key)) {
        seen.add(key);
        allJobs.push(job);
      }
    }
  }
  if (allOld) break;
  const maxPage = body.meta?.last_page || MAX_PAGES;
  if (page >= maxPage) break;
}

// Fail visibly if ALL requests errored
if (allJobs.length === 0 && errors.length > 0) {
  throw new Error(`AN: all ${errors.length} page requests failed after retries. First error: ${errors[0].error}`);
}

if (allJobs.length === 0) return [{ json: { _empty: true } }];

function parseSalary(job) {
  let min = job.salary_min || null;
  let max = job.salary_max || null;
  let currency = job.salary_currency || null;
  if (!min && job.salary) {
    const nums = String(job.salary).replace(/[.,]/g, '').match(/\d+/g);
    if (nums && nums.length >= 2) { min = Number(nums[0]); max = Number(nums[1]); }
    else if (nums && nums.length === 1) { min = Number(nums[0]); }
    if (!currency && /eur|€/i.test(job.salary)) currency = 'EUR';
    if (!currency && /usd|\$/i.test(job.salary)) currency = 'USD';
    if (!currency && /chf/i.test(job.salary)) currency = 'CHF';
    if (!currency && /gbp|£/i.test(job.salary)) currency = 'GBP';
  }
  return { salary_min: min, salary_max: max, salary_currency: currency || (min ? 'EUR' : null) };
}

const _crawlMeta = {
  source: 'arbeitnow',
  pages_fetched: lastPage,
  total_results: allJobs.length,
  fetch_errors: errors.length,
  errors: errors.slice(0, 10),
  circuit_broken: circuitBroken,
  circuit_breaker_stats: { total: totalRequests, failed: failedRequests },
};

const mapped = allJobs.map(j => {
  const desc = j.description || '';
  const sal = parseSalary(j);
  return { json: {
    source: 'arbeitnow',
    external_id: j.slug || '',
    url: j.url || `https://www.arbeitnow.com/view/${j.slug}`,
    title: j.title || '',
    company: j.company_name || '',
    location: j.location || '',
    description: desc,
    description_quality: (desc.length > 100) ? 'good' : 'poor',
    tags: j.tags || [],
    remote: j.remote || false,
    likely_english: isLikelyEnglish(desc),
    staffing_agency: detectStaffingAgency(j.company_name || ''),
    geo_mismatch: detectGeoMismatch(j.location || '', j.remote || false),
    _rawApiData: j,
    salary_min: sal.salary_min,
    salary_max: sal.salary_max,
    salary_currency: sal.salary_currency,
    start_date: null,
    posted_at: j.created_at ? new Date(j.created_at * 1000 || j.created_at).toISOString() : null,
  }};
});
if (mapped.length > 0) mapped[0].json._crawlMeta = _crawlMeta;
return mapped;
