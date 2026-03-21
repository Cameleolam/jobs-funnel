# Funnel - Setup Guide

## What is this

Funnel crawls German job boards, scores each posting against your profile,
auto-selects the right CV variant, generates tailored CVs and cover letters,
and logs everything to Google Sheets + Drive.

Jobs go in wide. Tailored applications come out narrow.

## Architecture

```
Your laptop (Windows + Git Bash)
│
├── n8n (native via npx, runs on localhost:5678)
│   ├── Manual trigger (click Execute)
│   ├── Bookmarklet webhook
│   └── Workflow nodes call Python wrapper scripts
│
├── ~/jobs_funnel/
│   ├── scripts/
│   │   ├── filter.py     → claude -p with filter prompt
│   │   ├── generate.py   → claude -p with generate prompt + base CV
│   │   └── parse.py      → claude -p to extract data from HTML
│   ├── cvs/
│   │   ├── backend.html   (CV_SOFTWAREENG)
│   │   ├── data.html      (CV_DATAENG)
│   │   ├── fullstack.html (CV_FS)
│   │   └── systems.html   (CV_SYSTENG)
│   ├── prompts/
│   │   ├── filter_prompt.md
│   │   └── generate_prompt.md
│   ├── output/             ← local copies of generated files
│   └── workflow.json
│
├── Claude Code (Max subscription, authenticated)
│   └── called via claude -p from Python scripts
│
└── Google Cloud (remote)
    ├── Google Sheets → Tracker spreadsheet
    └── Google Drive  → Generated CV/CL files
```

## Prerequisites

1. **Python 3.9+**: `python --version`
2. **Node.js 18+**: `node -v`
3. **Claude Code**: installed and authenticated
   - Test: `echo "Say OK" | claude -p --output-format text`
4. **Google account** for Sheets/Drive

## Step 1: Install n8n

```bash
npm install -g n8n
```

## Step 2: Set up the folder

Copy the `funnel/` directory to your home folder:

```bash
cp -r funnel ~/jobs_funnel
```

Or clone it if you've put it in a git repo.

The structure should be:
```
~/jobs_funnel/
  scripts/filter.py
  scripts/generate.py
  scripts/parse.py
  cvs/backend.html
  cvs/data.html
  cvs/fullstack.html
  cvs/systems.html
  prompts/filter_prompt.md
  prompts/generate_prompt.md
  output/
  workflow.json
```

## Step 3: Test the scripts

Open Git Bash or any terminal:

```bash
echo '{"title":"Python Backend Developer","company":"ExampleCo","location":"Hamburg","description":"We need a Python dev with Flask experience. 2-4 years. English working language."}' | python ~/jobs_funnel/scripts/filter.py
```

You should get back JSON with a fit_score, decision, and cv_variant.

If `claude` isn't found, find the full path (`where claude` on Windows)
and update the subprocess call in the scripts.

## Step 4: Google Sheet

1. Create a new Google Sheet
2. Rename the first tab to **Tracker**
3. Row 1 headers:

```
Date | Source | Company | Role | Location | Score | Decision | CV Variant | Blockers | Strong Matches | Reasoning | Status | Drive Link | Job URL | Notes
```

4. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`

## Step 5: Google Drive folder

1. Create a folder "Job Applications" in Drive
2. Copy the folder ID from the URL

## Step 6: Google OAuth for n8n

1. Go to console.cloud.google.com
2. Create a project (e.g., "Funnel")
3. Enable: Google Sheets API, Google Drive API
4. Credentials > Create > OAuth 2.0 Client ID > Web application
5. Add redirect URI: `http://localhost:5678/rest/oauth2-credential/callback`
6. Save Client ID and Client Secret

## Step 7: Start n8n and import

```bash
n8n start
```

Open http://localhost:5678

1. Settings > Credentials:
   - Add "Google Sheets OAuth2" (Client ID + Secret from step 6)
   - Add "Google Drive OAuth2" (same Client ID + Secret)
   - Complete OAuth flow for both
2. Workflows > Import from File > select `workflow.json`
3. Open the imported workflow

## Step 8: Replace placeholders

Find and replace in the workflow:

| Find | Replace with |
|---|---|
| `YOUR_SHEET_ID` | Your Google Sheet ID (3 nodes) |
| `YOUR_DRIVE_FOLDER_ID` | Your Drive folder ID (1 node) |

Assign Google credentials to these nodes:
- Dedup: Check Sheet → Google Sheets
- Sheet: Log SKIP/MAYBE → Google Sheets
- Sheet: Log PASS → Google Sheets
- Drive: Create Folder → Google Drive
- Drive: Upload Files → Google Drive

## Step 9: Run it

Click "Execute Workflow" in n8n. It will:
1. Query Arbeitsagentur + Arbeitnow APIs
2. Filter each job via claude -p
3. Generate tailored CV + cover letter for PASS jobs
4. Upload to Drive, log to Sheet

## Bookmarklet

Save as a browser bookmark:

```
javascript:void(fetch('http://localhost:5678/webhook/new-job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:location.href,title:document.title,notes:prompt('Notes?')||''})}).then(r=>r.ok?alert('Sent to Funnel!'):alert('Failed: '+r.status)))
```

Click it on any job posting page to send it through the pipeline.

## Troubleshooting

### claude not found in subprocess
Find the full path: `where claude` (cmd) or `which claude` (Git Bash).
Update the scripts: change `"claude"` to the full path, e.g.,
`"C:/Users/you/AppData/Roaming/npm/claude.cmd"`

### n8n Execute Command fails on Windows
n8n uses cmd.exe by default on Windows. If `python` isn't in your PATH for cmd,
use the full path to python in the workflow Execute Command nodes.

### Google OAuth redirect fails
Make sure the redirect URI is exactly:
`http://localhost:5678/rest/oauth2-credential/callback`
(http, not https)

### Rate limits on claude -p
Your Max sub has usage limits. If processing many jobs in one batch,
the Wait node between filter calls helps. If you still hit limits,
reduce the number of search queries or run in smaller batches.

## Migration to VPS

When ready:
1. Copy `~/jobs_funnel/` to VPS
2. Set up Docker + n8n + Caddy (see VPS setup files)
3. Replace the 3 Execute Command nodes with HTTP Request nodes
   calling the Anthropic API directly
4. Add API key as credential
5. Update Google OAuth redirect URI to your domain
6. Everything else (Sheet, Drive, prompts, CVs) stays identical