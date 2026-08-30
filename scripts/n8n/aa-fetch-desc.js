// Fetch full descriptions from Arbeitsagentur job details for new AA jobs (post-dedup).
// Non-AA jobs and AA jobs without a reference number pass through unchanged.
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));

const FETCH_DELAY = config.aa_fetch_delay_ms || 300;
const MAX_FETCHES = config.aa_max_fetches || 200;
const FETCH_TIMEOUT = config.aa_fetch_timeout_ms || 5000;
const DESC_MAX = config.description_max_chars || 5000;
const CB_THRESHOLD = config.circuit_breaker_threshold ?? 0.8;
const CB_MIN = 10;
const DETAIL_BASE = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails';
const HEADERS = { 'X-API-Key': 'jobboerse-jobsuche', 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' };

function checkDescriptionQuality(desc) {
  if (!desc || desc.length < 50) return 'empty';

  const lower = desc.toLowerCase();
  const len = desc.length;

  const junkPatterns = [
    'cookie', 'datenschutz', 'privacy policy', 'accept all',
    'page not found', '404', 'access denied', 'forbidden',
    'javascript is required', 'enable javascript',
    'please log in', 'bitte melden sie sich an',
    'captcha', 'robot'
  ];
  const junkHits = junkPatterns.filter(p => lower.includes(p)).length;
  if (junkHits >= 2) return 'poor';

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

const items = $input.all();
let fetchCount = 0;
let failCount = 0;
let circuitBroken = false;

for (const item of items) {
  const j = item.json;
  if (j.source !== 'arbeitsagentur') continue;
  const reference = j.external_id || j._rawApiData?.referenznummer;
  if (!reference) continue;
  if (fetchCount >= MAX_FETCHES) break;
  if (fetchCount >= CB_MIN && failCount / fetchCount >= CB_THRESHOLD) {
    circuitBroken = true;
    break;
  }
  if (fetchCount > 0) await new Promise(r => setTimeout(r, FETCH_DELAY));
  fetchCount++;
  let success = false;
  for (let attempt = 0; attempt <= 1 && !success; attempt++) {
    try {
      const encodedReference = Buffer.from(reference, 'utf8').toString('base64');
      const raw = await this.helpers.httpRequest({
        method: 'GET',
        url: `${DETAIL_BASE}/${encodedReference}`,
        headers: HEADERS,
        timeout: FETCH_TIMEOUT,
      });
      const detail = typeof raw === 'string' ? JSON.parse(raw) : raw;
      const desc = String(detail.stellenangebotsBeschreibung || '').trim();
      if (desc) {
        j.description = desc.substring(0, DESC_MAX);
        j.description_quality = checkDescriptionQuality(j.description);
      }
      j._rawApiData = { ...(j._rawApiData || {}), _jobDetails: detail };
      success = true;
    } catch (e) {
      if (attempt === 1) failCount++;
      else await new Promise(r => setTimeout(r, 500));
    }
  }
}

return items;
