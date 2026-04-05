# Funnel - Setup Guide

## What is this

Funnel crawls German job boards, scores each posting against your candidate profile,
auto-selects the right CV variant, and logs everything to PostgreSQL.

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
├── Claude Code (Max subscription, authenticated)
│   └── called via claude -p from Python scripts
│
└── PostgreSQL (local)
    └── jobs, pipeline_runs, job_raw_data tables
```

## Prerequisites

1. **Python 3.9+**: `python --version`
2. **Node.js 18+**: `node -v`
3. **PostgreSQL**: running locally with a `jobs_funnel` database
4. **Claude Code**: installed and authenticated (`claude --version`)

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

## Step 4: Set up the database

```bash
psql -U postgres -d jobs_funnel -f scripts/setup_db.sql
```

This creates the `jobs`, `pipeline_runs`, and `job_raw_data` tables.

## Step 5: Create and validate your profile

```bash
python scripts/setup_profile.py myprofile
# Edit the files it creates, then validate:
python scripts/validate_profile.py profiles/myprofile/
```

Checks that `search.json` and `filter_prompt.md` exist.
See `profiles/README.md` for the full guide and `templates/profile/` for the example files.

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
4. Score each job via `claude -p` (batches of 8)
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
javascript:void(fetch('http://localhost:5678/webhook/new-job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:location.href,title:document.title,notes:prompt('Notes?')||''})}).then(r=>r.ok?alert('Sent to Funnel!'):alert('Failed: '+r.status)))
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
| `batch_size` | 8 | Jobs per Claude filter batch |
| `dedup_cap` | 80 | Max pending jobs fetched per analyze iteration |
| `description_max_chars` | 5000 | Truncate descriptions beyond this length |
| `api_max_retries` | 2 | Max retry attempts per API request |
| `api_retry_delay_ms` | 1000 | Base delay between retries (exponential backoff) |
| `circuit_breaker_threshold` | 0.8 | Error rate threshold to trip circuit breaker |
| `circuit_breaker_min_requests` | 5 | Min requests before circuit breaker can trip |

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

## Troubleshooting

Common issues:
- **Claude calls hanging**: check `claude --version` works, try `claude -p "hello"` to verify auth
- **Preflight failures**: read the error — usually a missing env var or profile file
- **Dead letter jobs**: jobs that fail 3x get `status='dead'`. Fix the issue, then reset: `UPDATE jobs SET status='pending', error_count=0 WHERE status='dead';`

## License

MIT — see [LICENSE](LICENSE).
