// ATS Watchlist: poll configured company job-board APIs.
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = readJson(projectDir + '/config.json', {});
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = readJson(profileDir + '/search.json', {});
const watchlistPath = profileDir + '/company_watchlist.json';
const tempDir = projectDir + '/temp';
const statePath = tempDir + '/ats-watchlist-state.json';

const MIN_INTERVAL_HOURS = numberConfig('ats_watchlist_min_interval_hours', 23);
const COMPANY_DELAY_MS = numberConfig('ats_watchlist_company_delay_ms', 250);
const TIMEOUT_MS = numberConfig('ats_watchlist_timeout_ms', 10000);
const MAX_COMPANIES = Math.max(0, Math.floor(numberConfig('ats_watchlist_max_companies', 300)));
const MAX_JOBS_PER_COMPANY = Math.max(0, Math.floor(numberConfig('ats_watchlist_max_jobs_per_company', 25)));
const MAX_RETRIES = Math.max(0, Math.floor(numberConfig('api_max_retries', 2)));
const RETRY_DELAY = numberConfig('api_retry_delay_ms', 1000);

const countryCode = search.country || 'de';
const packDir = projectDir + '/countries/' + countryCode;
const staffingPack = readJson(packDir + '/staffing_patterns.json', { patterns: [] });
const geoPack = readJson(packDir + '/geo_allowlist.json', { allowlist: [] });
const langPack = readJson(packDir + '/language_hints.json', { languages: { en: { stopwords: [], threshold: 3, sample_chars: 500 } } });
const STAFFING_PATTERNS = staffingPack.patterns || [];
const GEO_ALLOWLIST = geoPack.allowlist || [];
const EN_HINTS = (langPack.languages && langPack.languages.en) || { stopwords: [], threshold: 3, sample_chars: 500 };

const DEFAULT_TITLE_KEYWORDS = [
  'backend', 'software engineer', 'python', 'data engineer',
  'automation engineer', 'ai engineer', 'ml engineer', 'full stack',
];
const DEFAULT_DESCRIPTION_KEYWORDS = [
  'python', 'django', 'fastapi', 'flask', 'etl', 'postgres',
  'workflow automation', 'llm', 'api integration',
];
const DEFAULT_NEGATIVE_KEYWORDS = [
  'intern', 'working student', 'werkstudent', 'trainee', 'apprentice',
  'unpaid', 'manager', 'director', 'vp ', 'vice president', 'head of',
  'principal', 'staff', 'lead', 'architect',
];
const HARD_NEGATIVE_KEYWORDS = [
  'legal', 'counsel', 'hr', 'people ops', 'recruiting', 'recruiter',
  'coordinator', 'social media', 'marketing', 'sales', 'account executive',
  'account manager', 'licensing', 'finance', 'ifrs', 'commercial',
  'privacy', 'm&a', 'customer success', 'business development',
];
const DESCRIPTION_FALLBACK_TITLE_KEYWORDS = [
  'engineer', 'developer', 'data', 'scientist', 'automation', 'platform',
  'software', 'devops', 'sre', 'ml', 'ai', 'backend', 'frontend',
  'full stack', 'fullstack', 'machine learning', 'qa', 'cloud',
  'infrastructure', 'research', 'systems', 'site reliability',
];

const titleKeywords = keywordList(search.ats_watchlist_title_keywords, DEFAULT_TITLE_KEYWORDS);
const descriptionKeywords = keywordList(search.ats_watchlist_description_keywords, DEFAULT_DESCRIPTION_KEYWORDS);
const negativeKeywords = Array.from(new Set(
  keywordList(search.ats_watchlist_negative_keywords, DEFAULT_NEGATIVE_KEYWORDS)
    .concat(HARD_NEGATIVE_KEYWORDS)
));

function readJson(path, fallback) {
  try {
    return JSON.parse(fs.readFileSync(path, 'utf-8'));
  } catch (e) {
    return fallback;
  }
}

function numberConfig(key, fallback) {
  const value = Number(config[key]);
  return Number.isFinite(value) ? value : fallback;
}

function keywordList(value, fallback) {
  const items = Array.isArray(value) && value.length > 0 ? value : fallback;
  return items.map(x => String(x).toLowerCase()).filter(Boolean);
}

function sleep(ms) {
  if (!ms || ms <= 0) return Promise.resolve();
  return new Promise(resolve => setTimeout(resolve, ms));
}

function emptyResult(meta) {
  return [{ json: { _empty: true, _crawlMeta: meta } }];
}

function shouldSkipByInterval() {
  if (!MIN_INTERVAL_HOURS || MIN_INTERVAL_HOURS <= 0) return false;
  const state = readJson(statePath, null);
  if (!state || !state.last_completed_at) return false;
  const completedAt = Date.parse(state.last_completed_at);
  if (!Number.isFinite(completedAt)) return false;
  const ageHours = (Date.now() - completedAt) / (60 * 60 * 1000);
  return ageHours >= 0 && ageHours < MIN_INTERVAL_HOURS;
}

function writeState(meta) {
  fs.mkdirSync(tempDir, { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify({
    last_completed_at: new Date(Date.now()).toISOString(),
    companies_succeeded: meta.companies_succeeded,
    total_results: meta.total_results,
    fetch_errors: meta.fetch_errors,
  }, null, 2));
}

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

function stripHtml(value) {
  return String(value || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function isoDate(value) {
  if (value == null || value === '') return null;
  const numberValue = Number(value);
  const parsed = Number.isFinite(numberValue) ? new Date(numberValue) : new Date(value);
  const time = parsed.getTime();
  return Number.isFinite(time) ? parsed.toISOString() : null;
}

function providerKey(provider) {
  return provider === 'lever_eu' ? 'lever_eu' : provider;
}

function requestFor(entry) {
  const slug = encodeURIComponent(entry.slug);
  if (entry.provider === 'greenhouse') {
    return `https://boards-api.greenhouse.io/v1/boards/${slug}/jobs?content=true`;
  }
  if (entry.provider === 'lever') {
    return `https://api.lever.co/v0/postings/${slug}?mode=json`;
  }
  if (entry.provider === 'lever_eu') {
    return `https://api.eu.lever.co/v0/postings/${slug}?mode=json`;
  }
  if (entry.provider === 'ashby') {
    return `https://api.ashbyhq.com/posting-api/job-board/${slug}?includeCompensation=true`;
  }
  throw new Error(`unknown ATS provider: ${entry.provider}`);
}

async function fetchWithRetry(opts) {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await this.helpers.httpRequest(opts);
    } catch (e) {
      const msg = e.message || String(e);
      const is4xx = /\b4\d{2}\b/.test(msg) || msg.includes('Bad Request') || msg.includes('Not Found');
      if (is4xx || attempt === MAX_RETRIES) throw e;
      await sleep(RETRY_DELAY * Math.pow(2, attempt));
    }
  }
}

function extractJobs(provider, body) {
  if (provider === 'lever' || provider === 'lever_eu') {
    return Array.isArray(body) ? body : (body.postings || []);
  }
  return body && Array.isArray(body.jobs) ? body.jobs : [];
}

function locationName(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  if (typeof value.name === 'string') return value.name;
  if (Array.isArray(value)) return value.map(locationName).filter(Boolean).join(', ');
  return '';
}

function isRemote(location) {
  const lower = String(location || '').toLowerCase();
  if (lower.includes('hybrid')) return false;
  return /\bremote\b/.test(lower);
}

function numberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function extractSalary(raw) {
  const compensation = raw.compensation || raw.compensationTierSummary || raw.salary || {};
  const salaryRange = compensation.salaryRange || compensation.range || compensation;
  const min = numberOrNull(salaryRange.min || salaryRange.minimum || salaryRange.minValue);
  const max = numberOrNull(salaryRange.max || salaryRange.maximum || salaryRange.maxValue);
  const currency = salaryRange.currencyCode || salaryRange.currency || compensation.currencyCode || compensation.currency || null;
  return {
    salary_min: min,
    salary_max: max,
    salary_currency: (min || max) && currency ? String(currency).toUpperCase() : null,
  };
}

function buildDescription(parts) {
  return parts.map(stripHtml).filter(Boolean).join('\n\n');
}

function mapGreenhouse(raw, entry) {
  const description = buildDescription([raw.content, raw.description]);
  const location = locationName(raw.location) || locationName(raw.offices);
  const salary = extractSalary(raw);
  return normalizeJob(raw, entry, {
    external_id: String(raw.id || ''),
    url: raw.absolute_url || raw.url || raw.internal_job_id || '',
    title: raw.title || '',
    company: raw.company_name || entry.company,
    location,
    description,
    tags: ['ats', 'greenhouse'].concat((raw.departments || []).map(d => d.name || d).filter(Boolean)),
    remote: isRemote(location),
    posted_at: isoDate(raw.updated_at || raw.first_published || raw.published_at),
    salary,
  });
}

function mapLever(raw, entry) {
  const categories = raw.categories || {};
  const listText = Array.isArray(raw.lists)
    ? raw.lists.map(list => buildDescription([list.text, list.content])).join('\n\n')
    : '';
  const description = buildDescription([raw.descriptionPlain, raw.description, listText]);
  const location = categories.location || locationName(raw.location);
  const salary = extractSalary(raw);
  return normalizeJob(raw, entry, {
    external_id: String(raw.id || ''),
    url: raw.hostedUrl || raw.applyUrl || raw.url || '',
    title: raw.text || raw.title || '',
    company: raw.company || entry.company,
    location,
    description,
    tags: ['ats', providerKey(entry.provider)].concat([categories.team, categories.department, categories.commitment].filter(Boolean)),
    remote: isRemote(location),
    posted_at: isoDate(raw.updatedAt || raw.createdAt),
    salary,
  });
}

function mapAshby(raw, entry) {
  const description = buildDescription([raw.descriptionPlain, raw.descriptionHtml, raw.description]);
  const location = locationName(raw.location);
  const salary = extractSalary(raw);
  return normalizeJob(raw, entry, {
    external_id: String(raw.id || ''),
    url: raw.jobUrl || raw.applyUrl || raw.url || '',
    title: raw.title || '',
    company: raw.companyName || entry.company,
    location,
    description,
    tags: ['ats', 'ashby'].concat([raw.department, raw.team, raw.employmentType].filter(Boolean)),
    remote: isRemote(location),
    posted_at: isoDate(raw.publishedAt || raw.updatedAt),
    salary,
  });
}

function normalizeJob(raw, entry, mapped) {
  const description = mapped.description || '';
  const company = mapped.company || entry.company || '';
  const remote = Boolean(mapped.remote);
  return {
    source: `ats_watchlist:${providerKey(entry.provider)}`,
    external_id: mapped.external_id || '',
    url: mapped.url || '',
    title: mapped.title || '',
    company,
    location: mapped.location || '',
    description,
    description_quality: description.length > 100 ? 'good' : (description.length > 0 ? 'poor' : 'empty'),
    tags: mapped.tags || ['ats', providerKey(entry.provider)],
    remote,
    likely_english: isLikelyEnglish(description),
    staffing_agency: detectStaffingAgency(company),
    geo_mismatch: detectGeoMismatch(mapped.location || '', remote),
    _rawApiData: raw,
    salary_min: mapped.salary.salary_min,
    salary_max: mapped.salary.salary_max,
    salary_currency: mapped.salary.salary_currency,
    start_date: null,
    posted_at: mapped.posted_at || null,
  };
}

function mapJob(raw, entry) {
  if (entry.provider === 'greenhouse') return mapGreenhouse(raw, entry);
  if (entry.provider === 'lever' || entry.provider === 'lever_eu') return mapLever(raw, entry);
  if (entry.provider === 'ashby') return mapAshby(raw, entry);
  throw new Error(`unknown ATS provider: ${entry.provider}`);
}

function containsKeyword(text, keywords) {
  const lower = String(text || '').toLowerCase();
  return keywords.some(keyword => lower.includes(keyword));
}

function hasBlockedLocation(location, description) {
  const lower = `${location || ''} ${description || ''}`.toLowerCase();
  const explicitOnly = [
    'us only', 'u.s. only', 'usa only', 'united states only',
    'canada only', 'uk only', 'united kingdom only', 'australia only',
  ];
  if (explicitOnly.some(term => lower.includes(term))) return true;
  const loc = String(location || '').toLowerCase().trim();
  return /^(remote\s*[-(]?\s*)?(us|u\.s\.|usa|united states|canada|uk|united kingdom|australia)(\s*only)?\)?$/.test(loc);
}

function hasGermanC1Requirement(text) {
  const lower = String(text || '').toLowerCase();
  return /(german|deutsch)[\s\w,.-]{0,40}\b(c1|c2)\b/.test(lower)
    || /\b(c1|c2)\b[\s\w,.-]{0,40}(german|deutsch)/.test(lower);
}

function shouldKeep(job) {
  const title = job.title || '';
  const description = job.description || '';
  if (containsKeyword(title, negativeKeywords)) return false;
  if (hasBlockedLocation(job.location, description)) return false;
  if (hasGermanC1Requirement(`${title}\n${description}`)) return false;
  const titleMatch = containsKeyword(title, titleKeywords);
  const descriptionFallback = containsKeyword(title, DESCRIPTION_FALLBACK_TITLE_KEYWORDS)
    && containsKeyword(description, descriptionKeywords);
  return titleMatch || descriptionFallback;
}

function dedupeKeys(job) {
  const url = String(job.url || '').trim().toLowerCase();
  const company = String(job.company || '').trim().toLowerCase();
  const title = String(job.title || '').trim().toLowerCase();
  return {
    url: url ? `url:${url}` : null,
    companyTitle: company || title ? `ct:${company}|${title}` : null,
  };
}

function enabledCompanies(watchlist) {
  return watchlist
    .filter(entry => entry && entry.enabled !== false)
    .slice(0, MAX_COMPANIES);
}

if (shouldSkipByInterval()) {
  return emptyResult({ source: 'ats_watchlist', skipped_by_interval: true });
}

if (!fs.existsSync(watchlistPath)) {
  return emptyResult({
    source: 'ats_watchlist',
    watchlist_missing: true,
    total_results: 0,
    companies_enabled: 0,
    companies_succeeded: 0,
    fetch_errors: 0,
    errors: [],
  });
}

const watchlist = readJson(watchlistPath, []);
if (!Array.isArray(watchlist)) {
  throw new Error('ATS Watchlist: company_watchlist.json must be an array');
}

const companies = enabledCompanies(watchlist);
if (companies.length === 0) {
  return emptyResult({
    source: 'ats_watchlist',
    total_results: 0,
    companies_enabled: 0,
    companies_succeeded: 0,
    fetch_errors: 0,
    errors: [],
  });
}

const allJobs = [];
const seenUrls = new Set();
const seenCompanyTitles = new Set();
const errors = [];
let companiesSucceeded = 0;
let companyCapsApplied = 0;

function jobRecency(job) {
  const time = Date.parse(job.posted_at || '');
  return Number.isFinite(time) ? time : 0;
}

for (const [index, entry] of companies.entries()) {
  if (index > 0) await sleep(COMPANY_DELAY_MS);
  try {
    const url = requestFor(entry);
    const body = await fetchWithRetry.call(this, {
      method: 'GET',
      url,
      json: true,
      timeout: TIMEOUT_MS,
    });
    companiesSucceeded++;

    const companyJobs = [];
    for (const raw of extractJobs(entry.provider, body)) {
      const job = mapJob(raw, entry);
      if (!shouldKeep(job)) continue;
      companyJobs.push(job);
    }

    companyJobs.sort((left, right) => jobRecency(right) - jobRecency(left));
    let companyAccepted = 0;
    for (const job of companyJobs) {
      const keys = dedupeKeys(job);
      if (keys.url && seenUrls.has(keys.url)) continue;
      if (keys.companyTitle && seenCompanyTitles.has(keys.companyTitle)) continue;
      if (MAX_JOBS_PER_COMPANY > 0 && companyAccepted >= MAX_JOBS_PER_COMPANY) {
        companyCapsApplied++;
        continue;
      }
      if (keys.url) seenUrls.add(keys.url);
      if (keys.companyTitle) seenCompanyTitles.add(keys.companyTitle);
      allJobs.push(job);
      companyAccepted++;
    }
  } catch (e) {
    errors.push({
      company: entry.company || '',
      provider: entry.provider || '',
      slug: entry.slug || '',
      error: e.message || String(e),
    });
  }
}

if (companiesSucceeded === 0 && errors.length > 0) {
  throw new Error(`ATS Watchlist: every enabled company failed. First error: ${errors[0].error}`);
}

const meta = {
  source: 'ats_watchlist',
  total_results: allJobs.length,
  companies_enabled: companies.length,
  companies_succeeded: companiesSucceeded,
  fetch_errors: errors.length,
  company_caps_applied: companyCapsApplied,
  errors: errors.slice(0, 20),
};

writeState(meta);

if (allJobs.length === 0) {
  return emptyResult(meta);
}

const mapped = allJobs.map(job => ({ json: job }));
mapped[0].json._crawlMeta = meta;
return mapped;
