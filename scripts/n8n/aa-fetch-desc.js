// Fetch full descriptions from employer pages for new AA jobs (post-dedup)
// AN jobs and AA jobs without externeUrl pass through unchanged.
const fs = require('fs');
const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '.').replace(/\\/g, '/');
const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));

const FETCH_DELAY = config.aa_fetch_delay_ms || 300;
const MAX_FETCHES = config.aa_max_fetches || 200;
const FETCH_TIMEOUT = config.aa_fetch_timeout_ms || 5000;
const DESC_MAX = config.description_max_chars || 5000;
const CB_THRESHOLD = config.circuit_breaker_threshold ?? 0.8;
const CB_MIN = 10;

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
        const items = Array.isArray(data) ? data : [data];
        for (const item of items) {
          if (item['@type'] === 'JobPosting' && item.description) {
            let desc = item.description.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
            desc = decodeEntities(desc);
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
  const extUrl = j._rawApiData?.externeUrl;
  if (!extUrl) continue;
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
      const html = await this.helpers.httpRequest({ method: 'GET', url: extUrl, encoding: 'utf-8', timeout: FETCH_TIMEOUT });
      const desc = extractDescription(html);
      if (desc) {
        j.description = desc;
        j.description_quality = checkDescriptionQuality(j.description);
      }
      success = true;
    } catch (e) {
      if (attempt === 1) failCount++;
      else await new Promise(r => setTimeout(r, 500));
    }
  }
}

return items;
