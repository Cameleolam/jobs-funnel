// Arbeitsagentur: run multiple server-side filtered searches + fetch full descriptions
const BASE = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs';
const HEADERS = { 'X-API-Key': 'jobboerse-jobsuche', 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' };

const searches = [
  'Python Developer', 'Backend Engineer', 'Data Engineer', 'Software Engineer',
  'Python Entwickler', 'Software Entwickler', 'Backend Entwickler',
  'ETL Developer', 'ETL Entwickler', 'Cloud Engineer',
  'Flask', 'Django', 'FastAPI', 'PHP Symfony', 'DevOps'
];
const commonParams = 'wo=Hamburg&umkreis=200&veroeffentlichtseit=30&pav=false&zeitarbeit=false&size=100';

const seenIds = new Set();
const jobs = [];
const errors = [];
const MAX_PAGES = 3;

for (let i = 0; i < searches.length; i++) {
  for (let page = 1; page <= MAX_PAGES; page++) {
    const url = `${BASE}?was=${encodeURIComponent(searches[i])}&${commonParams}&page=${page}`;
    let body;
    try {
      const raw = await this.helpers.httpRequest({ method: 'GET', url, headers: HEADERS });
      body = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (e) { errors.push({ search: searches[i], page, error: e.message || String(e) }); continue; }
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

if (jobs.length === 0) return [];

// Fetch full descriptions from employer pages (externeUrl)
function decodeEntities(text) {
  return text
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
}

const FETCH_DELAY = 300;
const MAX_FETCHES = 200;
let fetchCount = 0;
for (let i = 0; i < jobs.length && fetchCount < MAX_FETCHES; i++) {
  const extUrl = jobs[i].externeUrl;
  if (!extUrl) continue;
  if (fetchCount > 0) await new Promise(r => setTimeout(r, FETCH_DELAY));
  fetchCount++;
  try {
    const html = await this.helpers.httpRequest({ method: 'GET', url: extUrl, encoding: 'utf-8', timeout: 5000 });
    let text = String(html).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    text = decodeEntities(text);
    if (text.length > 100) jobs[i]._fullDesc = text.substring(0, 5000);
  } catch (e) { /* fall back to one-liner */ }
}

return jobs.map(j => {
  const company = typeof j.arbeitgeber === 'object' ? (j.arbeitgeber?.name || '') : (j.arbeitgeber || '');
  const location = j.arbeitsort?.ort || '';
  const region = j.arbeitsort?.region || '';
  const extUrl = j.externeUrl || '';
  const refUrl = j.refnr ? `https://www.arbeitsagentur.de/jobsuche/suche?id=${j.refnr}` : '';
  const url = extUrl || refUrl;
  const fallbackDesc = `${j.titel || ''} bei ${company} in ${location}${region ? ' (' + region + ')' : ''}. Beruf: ${j.beruf || ''}. Eintrittsdatum: ${j.eintrittsdatum || 'k.A.'}`;
  const desc = (j._fullDesc || fallbackDesc).substring(0, 5000);
  return { json: {
    source: 'arbeitsagentur',
    external_id: j.refnr || '',
    url: url,
    title: j.titel || '',
    company: company,
    location: location,
    description: desc,
    tags: [],
    remote: false,
    likely_english: false
  }};
});
