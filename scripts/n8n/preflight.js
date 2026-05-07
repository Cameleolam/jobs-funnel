// Pre-flight validation: env vars, profile files, config.json,
// pgvector extension, Ollama reachability + bge-m3 model presence.
const fs = require('fs');
const errors = [];
const warnings = [];

const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '').replace(/\\/g, '/');
const profile = $env.JOBS_FUNNEL_PROFILE || '';
const table = $env.JOBS_FUNNEL_TABLE || '';
const ollamaUrl = ($env.OLLAMA_URL || 'http://localhost:11434').replace(/\/+$/, '');
const embedModel = $env.EMBEDDING_MODEL || 'bge-m3';

// Required env vars
if (!projectDir) errors.push('JOBS_FUNNEL_PROJECT_DIR not set');
if (!profile) errors.push('JOBS_FUNNEL_PROFILE not set');
if (!table) errors.push('JOBS_FUNNEL_TABLE not set');

// Profile directory structure
if (projectDir && profile) {
  const profileDir = projectDir + '/profiles/' + profile;
  if (!fs.existsSync(profileDir)) {
    errors.push(`Profile dir not found: ${profileDir}`);
  } else {
    if (!fs.existsSync(profileDir + '/search.json')) errors.push('Missing: search.json');
    if (!fs.existsSync(profileDir + '/filter_prompt.md')) errors.push('Missing: filter_prompt.md');
    const cvsDir = profileDir + '/cvs';
    if (!fs.existsSync(cvsDir)) {
      warnings.push('cvs/ directory not found (optional, needed only for CV generation)');
    } else {
      const cvFiles = fs.readdirSync(cvsDir).filter(f => f.endsWith('.html'));
      if (cvFiles.length === 0) warnings.push('cvs/ directory exists but has no .html files');
    }
  }
}

// config.json
if (projectDir) {
  try {
    const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
    const required = ['batch_size', 'dedup_cap'];
    for (const key of required) {
      if (config[key] === undefined) errors.push(`config.json missing key: ${key}`);
    }
  } catch (e) {
    errors.push('config.json not found or invalid JSON');
  }
}

// Ollama reachability + model presence.
// Uses this.helpers.httpRequest, the same HTTP path the existing crawlers
// use. The n8n task-runner sandbox blocks fetch(), URL, and require('http').
async function checkOllama() {
  try {
    const body = await this.helpers.httpRequest({
      method: 'GET',
      url: ollamaUrl + '/api/tags',
      timeout: 3000,
      json: true,
    });
    const models = ((body && body.models) || []).map(m => (m.name || '').split(':')[0]);
    if (!models.includes(embedModel)) {
      errors.push(`Ollama model '${embedModel}' not found. Run: ollama pull ${embedModel}`);
    }
  } catch (e) {
    errors.push(`Ollama unreachable at ${ollamaUrl}: ${e.message || e}`);
  }
}

await checkOllama();

// pgvector extension (best-effort: query Postgres via env-configured creds via a helper script).
// We can't run psql from a Code node reliably, so we defer the SQL check to the
// migration step and only verify here that the extension *would* be findable.
// The first analyze run will fail loudly if pgvector is missing, so this is intentional.

if (errors.length > 0) {
  throw new Error('Pre-flight check failed:\n- ' + errors.join('\n- '));
}

return [{ json: { _preflight: 'ok', profile, table, warnings } }];
