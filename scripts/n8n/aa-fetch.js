// Arbeitsagentur: run multiple server-side filtered searches + fetch full descriptions
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
const profileDir = projectDir + '/profiles/' + ($env.JOBS_FUNNEL_PROFILE);
const search = JSON.parse(fs.readFileSync(profileDir + '/search.json', 'utf-8'));

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

for (const loc of locations) {
  const locParams = `wo=${encodeURIComponent(loc.location)}&umkreis=${loc.radius_km || 200}&veroeffentlichtseit=30&pav=false&zeitarbeit=false&size=100`;
  for (let i = 0; i < searches.length; i++) {
    for (let page = 1; page <= MAX_PAGES; page++) {
      const url = `${BASE}?was=${encodeURIComponent(searches[i])}&${locParams}&page=${page}`;
      let body;
      try {
        const raw = await fetchWithRetry.call(this, { method: 'GET', url, headers: HEADERS });
        body = typeof raw === 'string' ? JSON.parse(raw) : raw;
      } catch (e) {
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
  }
}

// Fail visibly if ALL requests errored (not just "no jobs found")
if (jobs.length === 0 && errors.length > 0) {
  throw new Error(`AA: all ${errors.length} requests failed after retries. First error: ${errors[0].error}`);
}

if (jobs.length === 0) return [];

// Fetch full descriptions from employer pages (externeUrl)
function decodeEntities(text) {
  return text
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
}

function extractDescription(html) {
  const str = String(html);

  // Try JSON-LD first (structured data, cleanest source)
  const jsonLdMatch = str.match(/<script[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi);
  if (jsonLdMatch) {
    for (const block of jsonLdMatch) {
      try {
        const content = block.replace(/<\/?script[^>]*>/gi, '');
        const data = JSON.parse(content);
        // Could be a single object or array
        const items = Array.isArray(data) ? data : [data];
        for (const item of items) {
          if (item['@type'] === 'JobPosting' && item.description) {
            // Description may be HTML, strip it
            let desc = item.description.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
            desc = decodeEntities(desc);
            // Also grab benefits/qualifications if available
            const extras = [item.qualifications, item.responsibilities, item.jobBenefits]
              .filter(Boolean).map(s => String(s).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());
            if (extras.length) desc += ' ' + extras.join(' ');
            if (desc.length > 100) return desc;
          }
        }
      } catch (e) { /* invalid JSON-LD, try next block */ }
    }
  }

  // Fallback: strip script/style blocks, then strip tags
  let text = str
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<nav[\s\S]*?<\/nav>/gi, ' ')
    .replace(/<header[\s\S]*?<\/header>/gi, ' ')
    .replace(/<footer[\s\S]*?<\/footer>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  text = decodeEntities(text);
  return text.length > 100 ? text : null;
}

function checkDescriptionQuality(desc) {
  if (!desc || desc.length < 50) return 'empty';

  const lower = desc.toLowerCase();
  const len = desc.length;

  // Junk patterns — cookie notices, login walls, error pages
  const junkPatterns = [
    'cookie', 'datenschutz', 'privacy policy', 'accept all',
    'page not found', '404', 'access denied', 'forbidden',
    'javascript is required', 'enable javascript',
    'please log in', 'bitte melden sie sich an',
    'captcha', 'robot'
  ];
  const junkHits = junkPatterns.filter(p => lower.includes(p)).length;
  if (junkHits >= 2) return 'poor';

  // Job-related keywords — a real posting should have several
  const jobKeywords = [
    'aufgaben', 'anforderungen', 'profil', 'qualifikation',
    'responsibilities', 'requirements', 'experience', 'skills',
    'benefits', 'salary', 'gehalt', 'team', 'position',
    'bewerben', 'apply', 'stellenangebot', 'job', 'rolle',
    'arbeiten', 'work', 'develop', 'engineer', 'manage'
  ];
  const jobHits = jobKeywords.filter(k => lower.includes(k)).length;

  if (len < 200 && jobHits < 2) return 'poor';
  if (len >= 200 && jobHits >= 2) return 'good';
  if (len >= 500) return 'good';

  return 'poor';
}

const FETCH_DELAY = config.aa_fetch_delay_ms || 300;
const MAX_FETCHES = config.aa_max_fetches || 200;
let fetchCount = 0;
let descFailCount = 0;
const descFailUrls = [];
for (let i = 0; i < jobs.length && fetchCount < MAX_FETCHES; i++) {
  const extUrl = jobs[i].externeUrl;
  if (!extUrl) continue;
  if (fetchCount > 0) await new Promise(r => setTimeout(r, FETCH_DELAY));
  fetchCount++;
  let success = false;
  // 1 retry for descriptions (nice-to-have)
  for (let attempt = 0; attempt <= 1 && !success; attempt++) {
    try {
      const html = await this.helpers.httpRequest({ method: 'GET', url: extUrl, encoding: 'utf-8', timeout: config.aa_fetch_timeout_ms || 5000 });
      const desc = extractDescription(html);
      if (desc) {
        jobs[i]._fullDesc = desc.substring(0, config.description_max_chars || 5000);
        jobs[i]._descriptionQuality = checkDescriptionQuality(jobs[i]._fullDesc);
      }
      success = true;
    } catch (e) {
      if (attempt === 1) {
        descFailCount++;
        descFailUrls.push(extUrl);
      } else {
        await new Promise(r => setTimeout(r, 500));
      }
    }
  }
}

const _crawlMeta = {
  source: 'arbeitsagentur',
  locations: locations.map(l => l.location),
  searches_run: searches.length * locations.length,
  total_results: jobs.length,
  fetch_errors: errors.length,
  errors: errors.slice(0, 10),
  descriptions_attempted: fetchCount,
  descriptions_failed: descFailCount,
  descriptions_failed_urls: descFailUrls.slice(0, 10),
};

const mapped = jobs.map(j => {
  const company = typeof j.arbeitgeber === 'object' ? (j.arbeitgeber?.name || '') : (j.arbeitgeber || '');
  const location = j.arbeitsort?.ort || '';
  const region = j.arbeitsort?.region || '';
  const extUrl = j.externeUrl || '';
  const refUrl = j.refnr ? `https://www.arbeitsagentur.de/jobsuche/suche?id=${j.refnr}` : '';
  const url = extUrl || refUrl;
  const fallbackDesc = `${j.titel || ''} bei ${company} in ${location}${region ? ' (' + region + ')' : ''}. Beruf: ${j.beruf || ''}. Eintrittsdatum: ${j.eintrittsdatum || 'k.A.'}`;
  const desc = (j._fullDesc || fallbackDesc).substring(0, config.description_max_chars || 5000);
  return { json: {
    source: 'arbeitsagentur',
    external_id: j.refnr || '',
    url: url,
    title: j.titel || '',
    company: company,
    location: location,
    description: desc,
    description_quality: j._descriptionQuality || (j._fullDesc ? 'unknown' : 'empty'),
    tags: [],
    remote: false,
    likely_english: false,
    _rawApiData: j,
    start_date: j.eintrittsdatum || null,
    posted_at: null
  }};
});
if (mapped.length > 0) mapped[0].json._crawlMeta = _crawlMeta;
return mapped;
