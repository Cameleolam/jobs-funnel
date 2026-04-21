// Himalayas: remote-jobs API, paginated via offset/limit.
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = JSON.parse(fs.readFileSync(profileDir + '/search.json', 'utf-8'));

const MAX_PAGES = config.himalayas_max_pages || 3;
const DELAY_MS = config.himalayas_delay_ms || 2000;
const PAGE_SIZE = 100;
const MAX_RETRIES = config.api_max_retries || 2;
const RETRY_DELAY = config.api_retry_delay_ms || 1000;
const cutoff = Date.now() - (config.an_days_back || 30) * 24 * 60 * 60 * 1000;

const STAFFING_PATTERNS = config.staffing_agency_patterns || [];
const GEO_ALLOWLIST = config.geo_allowlist || [];
const ENGLISH_STOPWORDS = ['the','and','you','we','team','experience','requirements','about','our','will','work','join','role','position'];
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
function isLikelyEnglish(description) {
  if (!description) return false;
  const sample = String(description).substring(0, 500).toLowerCase();
  return ENGLISH_STOPWORDS.filter(w => sample.includes(w)).length >= 3;
}

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

const titleKw = (search.himalayas_title_keywords || []).map(s => s.toLowerCase());
const tagKw = (search.himalayas_tag_keywords || []).map(s => s.toLowerCase());
const negKw = (search.himalayas_negative_keywords || []).map(s => s.toLowerCase());

const allJobs = [];
const seen = new Set();
const errors = [];
var lastPage = 0;
const CB_THRESHOLD = config.circuit_breaker_threshold ?? 0.8;
const CB_MIN = config.circuit_breaker_min_requests ?? 5;
let totalRequests = 0;
let failedRequests = 0;
let circuitBroken = false;

for (let page = 0; page < MAX_PAGES; page++) {
  if (page > 0) await new Promise(r => setTimeout(r, DELAY_MS));
  if (totalRequests >= CB_MIN && failedRequests / totalRequests >= CB_THRESHOLD) {
    circuitBroken = true;
    break;
  }
  lastPage = page + 1;
  const offset = page * PAGE_SIZE;
  let body;
  try {
    body = await fetchWithRetry.call(this, {
      method: 'GET',
      url: `https://himalayas.app/jobs/api?category=software&limit=${PAGE_SIZE}&offset=${offset}`,
      json: true,
    });
    totalRequests++;
  } catch (e) {
    totalRequests++;
    failedRequests++;
    errors.push({ page, error: e.message || String(e) });
    continue;
  }
  const data = body.jobs || [];
  if (data.length === 0) break;

  let allOld = true;
  for (const job of data) {
    const created = job.pubDate ? new Date(job.pubDate).getTime() : Date.now();
    if (created > cutoff) allOld = false;
    if (created <= cutoff) continue;

    const t = (job.title || '').toLowerCase();
    const cats = (job.categories || []).concat(job.parentCategories || []).map(x => String(x).toLowerCase());
    const titleMatch = titleKw.length === 0 || titleKw.some(k => t.includes(k));
    const tagMatch = tagKw.length === 0 || tagKw.some(k => cats.some(c => c.includes(k)));
    const negMatch = negKw.some(k => t.includes(k));
    if (negMatch) continue;
    if (!titleMatch && !tagMatch) continue;

    const key = job.guid || job.applicationLink || (job.companySlug + '|' + job.title);
    if (seen.has(key)) continue;
    seen.add(key);
    allJobs.push(job);
  }
  if (allOld) break;
}

if (allJobs.length === 0 && errors.length > 0) {
  throw new Error(`Himalayas: all ${errors.length} page requests failed after retries. First error: ${errors[0].error}`);
}

if (allJobs.length === 0) return [{ json: { _empty: true } }];

const _crawlMeta = {
  source: 'himalayas',
  pages_fetched: lastPage,
  total_results: allJobs.length,
  fetch_errors: errors.length,
  errors: errors.slice(0, 10),
  circuit_broken: circuitBroken,
  circuit_breaker_stats: { total: totalRequests, failed: failedRequests },
};

const mapped = allJobs.map(j => {
  const desc = j.description || j.excerpt || '';
  const company = j.companyName || '';
  const url = j.applicationLink || `https://himalayas.app/companies/${j.companySlug}/jobs/${encodeURIComponent((j.title || '').toLowerCase().replace(/\s+/g,'-'))}`;
  const loc = Array.isArray(j.locationRestrictions) && j.locationRestrictions.length > 0
    ? j.locationRestrictions.join(', ')
    : 'Remote';
  const seniorityArr = Array.isArray(j.seniority) ? j.seniority : [];
  const senior = seniorityArr.length > 0 ? String(seniorityArr[0]).toLowerCase() : null;
  return { json: {
    source: 'himalayas',
    external_id: j.guid || '',
    url: url,
    title: j.title || '',
    company: company,
    location: loc,
    description: desc,
    description_quality: (desc.length > 100) ? 'good' : 'poor',
    tags: (j.categories || []).concat(j.parentCategories || []),
    remote: true,
    likely_english: isLikelyEnglish(desc),
    staffing_agency: detectStaffingAgency(company),
    geo_mismatch: detectGeoMismatch(loc, true),
    _rawApiData: j,
    salary_min: j.minSalary || null,
    salary_max: j.maxSalary || null,
    salary_currency: j.currency || null,
    start_date: null,
    posted_at: j.pubDate ? new Date(j.pubDate).toISOString() : null,
  }};
});
if (mapped.length > 0) mapped[0].json._crawlMeta = _crawlMeta;
return mapped;
