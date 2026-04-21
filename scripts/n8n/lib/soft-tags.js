// Soft-tag detection helpers, mirror of scripts/lib/soft_tags.py.
// n8n Code nodes cannot require local files, so each crawler inlines
// these three functions. This file is the canonical reference.

const ENGLISH_STOPWORDS = ['the','and','you','we','team','experience','requirements','about','our','will','work','join','role','position'];

function detectStaffingAgency(company, patterns) {
  if (!company) return false;
  const lower = String(company).toLowerCase();
  return (patterns || []).some(p => lower.includes(String(p).toLowerCase()));
}

function detectGeoMismatch(location, remote, allowlist) {
  if (remote) return false;
  if (!location) return true;
  const lower = String(location).toLowerCase();
  return !(allowlist || []).some(a => lower.includes(String(a).toLowerCase()));
}

function isLikelyEnglish(description) {
  if (!description) return false;
  const sample = String(description).substring(0, 500).toLowerCase();
  const hits = ENGLISH_STOPWORDS.filter(w => sample.includes(w)).length;
  return hits >= 3;
}

module.exports = { detectStaffingAgency, detectGeoMismatch, isLikelyEnglish };
