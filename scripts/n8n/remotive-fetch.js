// Remotive: public JSON API, all remote, tech-focused.
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = JSON.parse(fs.readFileSync(profileDir + '/search.json', 'utf-8'));

const MAX_RETRIES = config.api_max_retries || 2;
const RETRY_DELAY = config.api_retry_delay_ms || 1000;
const cutoff = Date.now() - (config.an_days_back || 30) * 24 * 60 * 60 * 1000;

const countryCode = search.country || 'de';
const packDir = projectDir + '/countries/' + countryCode;
const staffingPack = JSON.parse(fs.readFileSync(packDir + '/staffing_patterns.json', 'utf-8'));
const geoPack = JSON.parse(fs.readFileSync(packDir + '/geo_allowlist.json', 'utf-8'));
const langPack = JSON.parse(fs.readFileSync(packDir + '/language_hints.json', 'utf-8'));
const STAFFING_PATTERNS = staffingPack.patterns || [];
const GEO_ALLOWLIST = geoPack.allowlist || [];
const EN_HINTS = (langPack.languages && langPack.languages.en) || { stopwords: [], threshold: 3, sample_chars: 500 };

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
  const sample = String(description).substring(0, EN_HINTS.sample_chars).toLowerCase();
  return EN_HINTS.stopwords.filter(w => sample.includes(w)).length >= EN_HINTS.threshold;
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

const titleKw = (search.remotive_title_keywords || []).map(s => s.toLowerCase());
const tagKw = (search.remotive_tag_keywords || []).map(s => s.toLowerCase());
const negKw = (search.remotive_negative_keywords || []).map(s => s.toLowerCase());

const allJobs = [];
const seen = new Set();
const errors = [];

let body;
try {
  body = await fetchWithRetry.call(this, {
    method: 'GET',
    url: 'https://remotive.com/api/remote-jobs?category=software-dev',
    json: true,
  });
} catch (e) {
  throw new Error(`Remotive: fetch failed after retries: ${e.message || e}`);
}

const data = body.jobs || [];
for (const job of data) {
  const createdStr = job.publication_date || job.pub_date;
  const created = createdStr ? new Date(createdStr).getTime() : Date.now();
  if (created < cutoff) continue;

  const t = (job.title || '').toLowerCase();
  const tags = (job.tags || []).map(x => String(x).toLowerCase());
  const titleMatch = titleKw.length === 0 || titleKw.some(k => t.includes(k));
  const tagMatch = tagKw.length === 0 || tagKw.some(k => tags.includes(k));
  const negMatch = negKw.some(k => t.includes(k));
  if (negMatch) continue;
  if (!titleMatch && !tagMatch) continue;

  const key = String(job.id || job.url || job.title);
  if (seen.has(key)) continue;
  seen.add(key);
  allJobs.push(job);
}

if (allJobs.length === 0) return [{ json: { _empty: true } }];

const _crawlMeta = {
  source: 'remotive',
  total_results: allJobs.length,
  fetch_errors: errors.length,
  errors: errors.slice(0, 10),
};

const mapped = allJobs.map(j => {
  const desc = j.description || '';
  const url = j.url || '';
  const location = j.candidate_required_location || 'Remote';
  const salaryStr = String(j.salary || '');
  let salary_min = null, salary_max = null, salary_currency = null;
  if (salaryStr) {
    const nums = salaryStr.replace(/[.,]/g, '').match(/\d+/g);
    if (nums && nums.length >= 2) { salary_min = Number(nums[0]); salary_max = Number(nums[1]); }
    else if (nums && nums.length === 1) { salary_min = Number(nums[0]); }
    if (/usd|\$/i.test(salaryStr)) salary_currency = 'USD';
    else if (/eur|€/i.test(salaryStr)) salary_currency = 'EUR';
    else if (/gbp|£/i.test(salaryStr)) salary_currency = 'GBP';
  }
  const company = j.company_name || '';
  return { json: {
    source: 'remotive',
    external_id: String(j.id || ''),
    url: url,
    title: j.title || '',
    company: company,
    location: location,
    description: desc,
    description_quality: (desc.length > 100) ? 'good' : 'poor',
    tags: j.tags || [],
    remote: true,
    likely_english: isLikelyEnglish(desc),
    staffing_agency: detectStaffingAgency(company),
    geo_mismatch: detectGeoMismatch(location, true),
    _rawApiData: j,
    salary_min: salary_min,
    salary_max: salary_max,
    salary_currency: salary_currency,
    start_date: null,
    posted_at: j.publication_date ? new Date(j.publication_date).toISOString() : null,
  }};
});
if (mapped.length > 0) mapped[0].json._crawlMeta = _crawlMeta;
return mapped;
