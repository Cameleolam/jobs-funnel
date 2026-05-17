# Jobs funnel - Setup Guide

## What is this

Jobs funnel crawls European and remote job boards (default country pack: Germany),
scores each posting against your candidate profile, auto-selects the right CV variant,
and logs everything to PostgreSQL.

Jobs go in wide. Scored, filtered candidates come out narrow.

## Architecture

```
Your laptop (Windows)
│
├── n8n (native via npx, runs on localhost:5678)
│   ├── Manual trigger / Cron (every 10 min)
│   └── "Analyze Only" webhook (re-process pending jobs, skip crawl)
│
├── jobs_funnel/
│   ├── scripts/          Python wrappers + build tooling
│   ├── templates/        Example profile (copy via setup script)
│   ├── profiles/         Per-candidate search terms, prompts, CVs
│   ├── workflow_template.json + scripts/n8n/*.js  ← edit these
│   └── workflow.json     ← built output, import into n8n
│
├── AI scoring CLI(s)
│   ├── Claude Code via claude -p
│   └── Codex CLI via codex exec
│
└── PostgreSQL (local)
    └── jobs, pipeline_runs, job_raw_data tables
```

## Country packs

Country-specific knowledge (staffing-agency names, geo allowlist, language hints) lives in
`countries/<code>/`. Profiles declare their country and which crawlers to run in `search.json`:

```json
{
  "country": "de",
  "crawlers": ["arbeitnow", "arbeitsagentur", "remotive", "arbeitnow_remote", "himalayas"]
}
```

The reference pack is `countries/de/` (Germany). `countries/global/` is a remote-only stub.
To add a new country, copy `countries/de/`, edit the four JSON files, and reference it from
your profile. See `countries/README.md` for details. After changing the crawler list, rebuild:
`python scripts/build_workflow.py`.

## Prerequisites

1. **Python 3.9+**: `python --version`
2. **Node.js 18+**: `node -v`
3. **Docker**: `docker --version` (for PostgreSQL)
4. **AI scoring CLI**: install and authenticate at least one provider:
   - Claude Code (`claude --version`)
   - Codex CLI (`codex --version`)

## Step 1: Install n8n

```bash
npm install -g n8n
```

## Step 2: Set up the Python environment

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate  # Linux/macOS
pip install -e .
```

## Step 3: Set up environment variables

Copy `.env.template` to `.env` and fill in the values:

```bash
cp .env.template .env
```

Key variables:
- `JOBS_FUNNEL_PROJECT_DIR` — absolute path to this directory
- `JOBS_FUNNEL_PROFILE` — profile name (whatever you named it in setup)
- `JOBS_FUNNEL_TABLE` — Postgres table name (e.g., `jobs`)
- `JOBS_FUNNEL_PG_*` — Postgres connection details
- `SCORING_PROVIDER` — primary AI scorer (`claude_sonnet`, `claude_haiku`, `codex_gpt55_high`, `codex_gpt55_xhigh`, or `ollama_local`)
- `SCORING_REVIEW_PROVIDER` — optional secondary reviewer for borderline scores

## Step 4: Create and validate your profile

```bash
python scripts/setup_profile.py myprofile
# Edit the files it creates, then validate:
python scripts/validate_profile.py profiles/myprofile/
```

Checks that `search.json` and `filter_prompt.md` exist.
See `profiles/README.md` for the full guide and `templates/profile/` for the example files.

## Step 5: Start PostgreSQL and apply migrations

```bash
docker compose up -d
```

Make sure `.env` has the intended `JOBS_FUNNEL_PROFILE` and `JOBS_FUNNEL_TABLE`, then
apply the baseline schema plus any unapplied migrations:

```bash
python scripts/run_migrations.py
```

The migration runner resolves table placeholders for your active profile and creates the
baseline tables such as `jobs`, `pipeline_runs`, and `job_raw_data`.

## Step 6: Test the filter script

```bash
echo '{"title":"Python Backend Developer","company":"ExampleCo","location":"Hamburg","description":"We need a Python dev with Flask. 2-4 years. English working language."}' | python scripts/filter.py
```

You should get back JSON with `fit_score`, `decision`, and `cv_variant`.

## Step 7: Start n8n and import

```bash
start.bat
```

Or manually:
```bash
n8n start
```

Open http://localhost:5678

1. Settings → Credentials:
   - Add "Postgres - Jobs Funnel" with your `JOBS_FUNNEL_PG_*` values
2. Workflows → Import from File → select `workflow.json`
3. Open the workflow, update credential references

## Step 8: Run it

Click "Execute Workflow" (or trigger cron). The pipeline will:

1. Validate environment (preflight)
2. Crawl Arbeitsagentur + Arbeitnow APIs
3. Deduplicate against Postgres, insert new jobs
4. Score each job via the selected scoring provider (batches of 8)
5. Run semantic duplicate detection
6. Log run stats to `pipeline_runs`

## Review UI

```bash
# With the venv activated (see Step 2):
python -m uvicorn ui.server:app --port 8080 --reload
```

Open http://localhost:8080 to browse scored jobs, make decisions, and export to Excel.

## Bookmarklet (manual job submission)

```javascript
javascript:void(fetch('http://localhost:5678/webhook/new-job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:location.href,title:document.title,notes:prompt('Notes?')||''})}).then(r=>r.ok?alert('Sent to Jobs funnel!'):alert('Failed: '+r.status)))
```

Click it on any job posting page to send it through the pipeline manually.

## Configuration (config.json)

Tunable pipeline constants. JS nodes read these at runtime.

| Key | Default | Purpose |
|-----|---------|---------|
| `model` | `claude-sonnet-4-6` | Claude model for scoring and dedup. Alternatives: `claude-haiku-4-5-20251001` (faster/cheaper), `claude-opus-4-6` (best quality) |
| `aa_max_pages` | 3 | Max pagination pages per AA search |
| `aa_max_fetches` | 200 | Max AA description fetches per run |
| `aa_fetch_delay_ms` | 300 | Delay between AA description fetches |
| `aa_fetch_timeout_ms` | 5000 | Timeout per AA description fetch |
| `an_max_pages` | 10 | Max Arbeitnow pagination pages |
| `an_delay_ms` | 5000 | Delay between AN page fetches |
| `an_days_back` | 30 | Only include jobs posted within N days |
| `batch_size` | 8 | Jobs per filter batch |
| `dedup_cap` | 80 | Max pending jobs fetched per analyze iteration |
| `description_max_chars` | 5000 | Truncate descriptions beyond this length |
| `api_max_retries` | 2 | Max retry attempts per API request |
| `api_retry_delay_ms` | 1000 | Base delay between retries (exponential backoff) |
| `circuit_breaker_threshold` | 0.8 | Error rate threshold to trip circuit breaker |
| `circuit_breaker_min_requests` | 5 | Min requests before circuit breaker can trip |

## Scoring provider configuration (.env)

Scoring is selected through environment variables, not `config.json`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCORING_PROVIDER` | `codex_gpt55_high` | Primary scorer used for every job |
| `SCORING_REVIEW_PROVIDER` | empty | Optional secondary reviewer |
| `SCORING_REVIEW_LOW` | `4` | Lowest score that should be reviewed |
| `SCORING_REVIEW_HIGH` | `6` | Highest score that should be reviewed |
| `SCORING_REVIEW_MAX_PER_BATCH` | `8` | Max reviewer calls per filter batch |
| `SCORING_WRAPPER_TIMEOUT_SECONDS` | `3600` | Timeout for the full `run_filter.py` wrapper |
| `SCORING_CLAUDE_CMD` | `claude` | Claude CLI command |
| `SCORING_CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude Sonnet model name |
| `SCORING_HAIKU_MODEL` | `haiku` | Claude Haiku model name |
| `SCORING_CODEX_CMD` | `codex` | Codex CLI command, or full `.cmd` path on Windows |
| `SCORING_CODEX_MODEL` | `gpt-5.5` | Codex model name |
| `SCORING_OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `SCORING_OLLAMA_MODEL` | empty | Local Ollama model name when using `ollama_local` |

Available providers:

- `claude_sonnet`: Claude CLI with Sonnet.
- `claude_haiku`: Claude CLI with Haiku.
- `codex_gpt55_high`: Codex CLI with GPT-5.5 and high reasoning.
- `codex_gpt55_xhigh`: Codex CLI with GPT-5.5 and xhigh reasoning.
- `ollama_local`: local Ollama model, only active when `SCORING_OLLAMA_MODEL` is set.

Example: Codex as primary scorer, Claude as the secondary reviewer for borderline scores:

```env
SCORING_PROVIDER=codex_gpt55_high
SCORING_REVIEW_PROVIDER=claude_sonnet
SCORING_REVIEW_LOW=4
SCORING_REVIEW_HIGH=6
SCORING_REVIEW_MAX_PER_BATCH=8
SCORING_CODEX_CMD=codex
SCORING_CODEX_MODEL=gpt-5.5
SCORING_CLAUDE_CMD=claude
SCORING_CLAUDE_MODEL=claude-sonnet-4-6
SCORING_WRAPPER_TIMEOUT_SECONDS=3600
```

With this setup, Codex scores every job. Claude only reviews Codex results whose `fit_score`
is between 4 and 6 inclusive. Scores outside that band do not consume Claude usage. The
secondary provider is a reviewer, not a failover path; if the primary provider fails, the
job keeps the provider error instead of automatically retrying on the secondary provider.

## Calibration Proposals

Calibration Proposals are DB-backed runtime overrides for scoring calibration.
They do not fine-tune a model and they do not generate CVs or cover letters.

Run all unapplied migrations for the active profile table:

```bash
python scripts/run_migrations.py
```

Then open the UI and go to `/calibration`.

The page can generate a proposal from local outcomes, apply it explicitly, and
roll back to the previous active settings. Applying a proposal updates
`<JOBS_FUNNEL_TABLE>_calibration_settings`; it does not edit `.env` and does
not rewrite historical job scores.

Runtime lookup order is:

1. active DB-backed calibration settings
2. `.env` values
3. code defaults

If the settings table is missing or unavailable, scoring falls back to the
current env/default behavior. A failed settings lookup is bounded by
`CALIBRATION_SETTINGS_DB_TIMEOUT_SECONDS` and retried after the fallback cache
TTL (`CALIBRATION_SETTINGS_FALLBACK_CACHE_SECONDS`).

## Scripts interface

The core scripts follow the same pattern: JSON in (file arg or stdin), JSON out (stdout), errors as JSON with `"error"` field + non-zero exit code.

```bash
# Filter (direct)
python scripts/filter.py job.json
echo '{"title":"..."}' | python scripts/filter.py

# Filter (via wrapper, used by n8n)
python scripts/run_filter.py <project_dir> <base64_data>
python scripts/run_filter.py <project_dir> --file <json_file_path>
```

## Editing the workflow

Never edit `workflow.json` directly. Edit the template and JS files, then rebuild:

```bash
# Edit workflow_template.json and/or scripts/n8n/*.js, then:
python scripts/build_workflow.py
# Re-import workflow.json into n8n
```

Rebuild and reimport `workflow.json` only after changing `workflow_template.json`,
`scripts/n8n/*.js`, or crawler selections in `profiles/<profile>/search.json`.
Python script, UI, README, and migration changes do not require n8n workflow reimport.

## Troubleshooting

Run setup diagnostics:

```bash
python scripts/doctor.py
```

Common issues:
- **Codex calls failing on Windows**: set `SCORING_CODEX_CMD` to the full `.cmd` path, for example `C:\Users\<you>\AppData\Roaming\npm\codex.cmd`
- **Claude calls hanging when configured**: check `claude --version` works, try `claude -p "hello"` to verify auth
- **Review provider not running**: confirm `SCORING_REVIEW_PROVIDER` is set and the base `fit_score` is between `SCORING_REVIEW_LOW` and `SCORING_REVIEW_HIGH`
- **Preflight failures**: read the error — usually a missing env var or profile file
- **Dead letter jobs**: jobs that fail 3x get `status='dead'`. Fix the issue, then reset: `UPDATE jobs SET status='pending', error_count=0 WHERE status='dead';`

## License

MIT — see [LICENSE](LICENSE).
