// Arbeitsagentur: run multiple server-side filtered searches + fetch full descriptions
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = JSON.parse(fs.readFileSync(profileDir + '/search.json', 'utf-8'));

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

const BASE = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs';
const HEADERS = { 'X-API-Key': 'jobboerse-jobsuche', 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' };
const MAX_RETRIES = config.api_max_retries || 2;
const RETRY_DELAY = config.api_retry_delay_ms || 1000;

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

const searches = search.aa_searches || [];
// Support multiple locations: aa_locations array or legacy aa_location string
const locations = search.aa_locations || [
  { location: search.aa_location, radius_km: search.aa_radius_km }
];

const seenIds = new Set();
const jobs = [];
const errors = [];
const MAX_PAGES = config.aa_max_pages || 3;
const CB_THRESHOLD = config.circuit_breaker_threshold ?? 0.8;
const CB_MIN = config.circuit_breaker_min_requests ?? 5;
let searchTotal = 0;
let searchFailed = 0;
let circuitBroken = false;

for (const loc of locations) {
  const locParams = `wo=${encodeURIComponent(loc.location)}&umkreis=${loc.radius_km || 200}&veroeffentlichtseit=30&pav=false&zeitarbeit=false&size=100`;
  for (let i = 0; i < searches.length; i++) {
    for (let page = 1; page <= MAX_PAGES; page++) {
      if (searchTotal >= CB_MIN && searchFailed / searchTotal >= CB_THRESHOLD) {
        circuitBroken = true;
        break;
      }
      const url = `${BASE}?was=${encodeURIComponent(searches[i])}&${locParams}&page=${page}`;
      let body;
      try {
        const raw = await fetchWithRetry.call(this, { method: 'GET', url, headers: HEADERS });
        body = typeof raw === 'string' ? JSON.parse(raw) : raw;
        searchTotal++;
      } catch (e) {
        searchTotal++;
        searchFailed++;
        errors.push({ location: loc.location, search: searches[i], page, error: e.message || String(e) });
        continue;
      }
      const results = body.stellenangebote || [];
      if (results.length === 0) break;
      for (const s of results) {
        const id = s.refnr || s.titel;
        if (!seenIds.has(id)) { seenIds.add(id); jobs.push(s); }
      }
      const maxPage = body.maxErgebnisse ? Math.ceil(body.maxErgebnisse / 100) : 1;
      if (page >= maxPage) break;
    }
    if (circuitBroken) break;
  }
  if (circuitBroken) break;
}

// Fail visibly if ALL requests errored (not just "no jobs found")
if (jobs.length === 0 && errors.length > 0) {
  throw new Error(`AA: all ${errors.length} requests failed after retries. First error: ${errors[0].error}`);
}

if (jobs.length === 0) return [{ json: { _empty: true } }];

const _crawlMeta = {
  source: 'arbeitsagentur',
  locations: locations.map(l => l.location),
  searches_run: searches.length * locations.length,
  total_results: jobs.length,
  fetch_errors: errors.length,
  errors: errors.slice(0, 10),
  circuit_broken: circuitBroken,
  circuit_breaker_stats: {
    search: { total: searchTotal, failed: searchFailed },
  },
};

const mapped = jobs.map(j => {
  const company = typeof j.arbeitgeber === 'object' ? (j.arbeitgeber?.name || '') : (j.arbeitgeber || '');
  const location = j.arbeitsort?.ort || '';
  const region = j.arbeitsort?.region || '';
  const extUrl = j.externeUrl || '';
  const refUrl = j.refnr ? `https://www.arbeitsagentur.de/jobsuche/suche?id=${j.refnr}` : '';
  const url = extUrl || refUrl;
  const fallbackDesc = `${j.titel || ''} bei ${company} in ${location}${region ? ' (' + region + ')' : ''}. Beruf: ${j.beruf || ''}. Eintrittsdatum: ${j.eintrittsdatum || 'k.A.'}`;
  return { json: {
    source: 'arbeitsagentur',
    external_id: j.refnr || '',
    url: url,
    title: j.titel || '',
    company: company,
    location: location,
    description: fallbackDesc,
    description_quality: 'empty',
    tags: [],
    remote: false,
    likely_english: isLikelyEnglish(fallbackDesc),
    staffing_agency: detectStaffingAgency(company),
    geo_mismatch: detectGeoMismatch(location, false),
    _rawApiData: j,
    start_date: j.eintrittsdatum || null,
    posted_at: null
  }};
});
if (mapped.length > 0) mapped[0].json._crawlMeta = _crawlMeta;
return mapped;
