// Arbeitnow: paginate up to 10 pages, relaxed client-side filters
const MAX_PAGES = 10;
const DELAY_MS = 5000;
const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;

const titleKw = ['python','backend','back-end','back end','data engineer','data engineering','software engineer','software developer','platform engineer','api developer','developer python','entwickler','softwareentwickler','devops','site reliability','sre','etl','junior developer','junior engineer','flask','django','fastapi','developer','engineer','cloud','infrastructure','programmierer','informatiker','application engineer','system engineer','web developer','webentwickler','it engineer','automation','machine learning','ml engineer','data scientist','data analyst','full stack','fullstack'];
const tagKw = ['python','backend','data','engineering','devops','api','flask','django','fastapi','docker','aws','postgresql','kubernetes','linux','sql','java','node','typescript','go','rust','cloud','azure','gcp','terraform','ci/cd','microservices'];
const locKw = ['hamburg','berlin','germany','remote','deutschland','münchen','munich','frankfurt','köln','cologne','deutsch','düsseldorf','hannover','stuttgart','bremen','nürnberg','nuremberg','leipzig','dresden','essen','dortmund','bonn','karlsruhe','mannheim','freiburg','heidelberg','europe','eu','dach'];
const negKw = ['manager','consultant','designer','marketing','sales','recruiter','sap','sap consultant','abap','salesforce','product owner','scrum master','project manager','buchhalter','accounting','finance','legal','rechtsanwalt','jurist','pflege','nurse','arzt','physician','lehrer','teacher','werkstudent','working student','dual student','intern','praktikant','trainee','senior director','vp ','vice president','head of','chief','principal','staff engineer','lead architect'];
const engWords = ['the','and','you','we','team','experience','requirements','about','our','will','work','join','role','position'];

function isLikelyEnglish(desc) {
  const sample = (desc || '').substring(0, 500).toLowerCase();
  const hits = engWords.filter(w => sample.includes(w)).length;
  return hits >= 3;
}

const allJobs = [];
const seen = new Set();

for (let page = 1; page <= MAX_PAGES; page++) {
  if (page > 1) await new Promise(r => setTimeout(r, DELAY_MS));
  let body;
  try {
    body = await this.helpers.httpRequest({ method: 'GET', url: `https://www.arbeitnow.com/api/job-board-api?page=${page}`, json: true });
  } catch (e) { break; }
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
  const lastPage = body.meta?.last_page || MAX_PAGES;
  if (page >= lastPage) break;
}

if (allJobs.length === 0) return [];

return allJobs.map(j => {
  const desc = (j.description || '').substring(0, 5000);
  return { json: {
    source: 'arbeitnow',
    external_id: j.slug || '',
    url: j.url || `https://www.arbeitnow.com/view/${j.slug}`,
    title: j.title || '',
    company: j.company_name || '',
    location: j.location || '',
    description: desc,
    tags: j.tags || [],
    remote: j.remote || false,
    likely_english: isLikelyEnglish(desc)
  }};
});
