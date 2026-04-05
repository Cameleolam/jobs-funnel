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

## Step 2: Set up environment variables

Copy `.env.template` to `.env` and fill in the values:

```bash
cp .env.template .env
```

Key variables:
- `JOBS_FUNNEL_PROJECT_DIR` — absolute path to this directory
- `JOBS_FUNNEL_PROFILE` — profile name (whatever you named it in setup)
- `JOBS_FUNNEL_TABLE` — Postgres table name (e.g., `jobs`)
- `JOBS_FUNNEL_PG_*` — Postgres connection details

## Step 3: Set up the database

```bash
psql -U postgres -d jobs_funnel -f scripts/setup_db.sql
```

This creates the `jobs`, `pipeline_runs`, and `job_raw_data` tables.

## Step 4: Create and validate your profile

```bash
python scripts/setup_profile.py myprofile
# Edit the files it creates, then validate:
python scripts/validate_profile.py profiles/myprofile/
```

Checks that `search.json` and `filter_prompt.md` exist.
See `profiles/README.md` for the full guide and `templates/profile/` for the example files.

## Step 5: Test the filter script

```bash
echo '{"title":"Python Backend Developer","company":"ExampleCo","location":"Hamburg","description":"We need a Python dev with Flask. 2-4 years. English working language."}' | python scripts/filter.py
```

You should get back JSON with `fit_score`, `decision`, and `cv_variant`.

## Step 6: Start n8n and import

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

## Step 7: Run it

Click "Execute Workflow" (or trigger cron). The pipeline will:

1. Validate environment (preflight)
2. Crawl Arbeitsagentur + Arbeitnow APIs
3. Deduplicate against Postgres, insert new jobs
4. Score each job via `claude -p` (batches of 8)
5. Run semantic duplicate detection
6. Log run stats to `pipeline_runs`

## Review UI

```bash
pip install -r ui/requirements.txt
python -m uvicorn ui.server:app --port 8080 --reload
```

Open http://localhost:8080 to browse scored jobs, make decisions, and export to Excel.

## Bookmarklet (manual job submission)

```javascript
javascript:void(fetch('http://localhost:5678/webhook/new-job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:location.href,title:document.title,notes:prompt('Notes?')||''})}).then(r=>r.ok?alert('Sent to Funnel!'):alert('Failed: '+r.status)))
```

Click it on any job posting page to send it through the pipeline manually.

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
