// Pre-flight validation: check env vars, profile files, config.json
const fs = require('fs');
const errors = [];

const projectDir = ($env.JOBS_FUNNEL_PROJECT_DIR || '').replace(/\\/g, '/');
const profile = $env.JOBS_FUNNEL_PROFILE || '';
const table = $env.JOBS_FUNNEL_TABLE || '';

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
      errors.push('Missing: cvs/ directory');
    } else {
      const cvFiles = fs.readdirSync(cvsDir).filter(f => f.endsWith('.html'));
      if (cvFiles.length === 0) errors.push('No .html files in cvs/ directory');
    }
  }
}

// config.json
if (projectDir) {
  try {
    const config = JSON.parse(fs.readFileSync(projectDir + '/config.json', 'utf-8'));
    const required = ['batch_size', 'dedup_cap', 'description_max_chars'];
    for (const key of required) {
      if (config[key] === undefined) errors.push(`config.json missing key: ${key}`);
    }
  } catch (e) {
    errors.push('config.json not found or invalid JSON');
  }
}

if (errors.length > 0) {
  throw new Error('Pre-flight check failed:\n- ' + errors.join('\n- '));
}

return [{ json: { _preflight: 'ok', profile, table } }];
