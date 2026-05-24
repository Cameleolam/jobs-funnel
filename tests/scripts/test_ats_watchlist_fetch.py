import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_project(tmp_path: Path, watchlist, *, config=None, search=None):
    write_json(
        tmp_path / "config.json",
        {
            "api_max_retries": 0,
            "api_retry_delay_ms": 0,
            "ats_watchlist_min_interval_hours": 23,
            "ats_watchlist_company_delay_ms": 0,
            "ats_watchlist_timeout_ms": 1000,
            "ats_watchlist_max_companies": 300,
            **(config or {}),
        },
    )
    write_json(
        tmp_path / "profiles" / "profile1" / "search.json",
        {
            "country": "de",
            "ats_watchlist_title_keywords": [
                "backend",
                "software engineer",
                "ai engineer",
            ],
            "ats_watchlist_description_keywords": [
                "python",
                "workflow automation",
                "llm",
                "api integration",
            ],
            "ats_watchlist_negative_keywords": [
                "intern",
                "working student",
                "manager",
                "director",
                "principal",
                "staff",
                "lead",
                "head of",
            ],
            **(search or {}),
        },
    )
    write_json(tmp_path / "profiles" / "profile1" / "company_watchlist.json", watchlist)
    write_json(tmp_path / "countries" / "de" / "staffing_patterns.json", {"patterns": ["recruiting"]})
    write_json(tmp_path / "countries" / "de" / "geo_allowlist.json", {"allowlist": ["berlin", "hamburg", "remote", "germany"]})
    write_json(
        tmp_path / "countries" / "de" / "language_hints.json",
        {
            "languages": {
                "en": {
                    "stopwords": ["the", "and", "you", "we", "team", "experience", "role"],
                    "threshold": 2,
                    "sample_chars": 500,
                }
            }
        },
    )
    return tmp_path


def run_ats_fetch(project_dir: Path, *, responses=None, failures=None):
    harness = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const code = fs.readFileSync('scripts/n8n/ats-watchlist-fetch.js', 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const fn = new AsyncFunction('$env', 'require', 'setTimeout', code);
const requests = [];
const failures = new Set(input.failures || []);
const responses = input.responses || {};
const context = {
  helpers: {
    httpRequest: async (opts) => {
      requests.push(opts.url);
      if (failures.has(opts.url)) throw new Error(`forced failure for ${opts.url}`);
      if (!(opts.url in responses)) throw new Error(`missing fake response for ${opts.url}`);
      return responses[opts.url];
    }
  }
};
function immediateTimeout(callback) {
  callback();
  return 0;
}
Promise.resolve(fn.call(
  context,
  {
    JOBS_FUNNEL_PROJECT_DIR: input.projectDir,
    JOBS_FUNNEL_PROFILE: 'profile1'
  },
  require,
  immediateTimeout
)).then(
  result => process.stdout.write(JSON.stringify({ result, requests })),
  error => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  }
);
"""
    return subprocess.run(
        ["node", "-e", harness],
        cwd=REPO,
        input=json.dumps(
            {
                "projectDir": str(project_dir),
                "responses": responses or {},
                "failures": failures or [],
            }
        ),
        capture_output=True,
        text=True,
    )


def test_ats_watchlist_normalizes_greenhouse_lever_and_ashby_jobs(tmp_path):
    greenhouse_url = "https://boards-api.greenhouse.io/v1/boards/examplegreen/jobs?content=true"
    lever_url = "https://api.lever.co/v0/postings/examplelever?mode=json"
    ashby_url = "https://api.ashbyhq.com/posting-api/job-board/exampleashby?includeCompensation=true"
    project_dir = make_project(
        tmp_path,
        [
            {"company": "Green Co", "provider": "greenhouse", "slug": "examplegreen"},
            {"company": "Lever Co", "provider": "lever", "slug": "examplelever"},
            {"company": "Ashby Co", "provider": "ashby", "slug": "exampleashby"},
        ],
    )

    result = run_ats_fetch(
        project_dir,
        responses={
            greenhouse_url: {
                "jobs": [
                    {
                        "id": 111,
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/examplegreen/jobs/111",
                        "location": {"name": "Remote - Germany"},
                        "content": "Join the team and build Python APIs for the role.",
                        "updated_at": "2026-05-20T10:00:00Z",
                    },
                    {
                        "id": 112,
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/examplegreen/jobs/112",
                        "location": {"name": "Remote - Germany"},
                        "content": "Duplicate company and title with a different URL",
                    },
                ]
            },
            lever_url: [
                {
                    "id": "lev-1",
                    "text": "Software Engineer",
                    "hostedUrl": "https://jobs.lever.co/examplelever/lev-1",
                    "categories": {"location": "Berlin", "team": "Engineering"},
                    "descriptionPlain": "You will build Python API integration and workflow automation.",
                    "createdAt": 1770000000000,
                },
                {
                    "id": "lev-2",
                    "text": "Marketing Manager",
                    "hostedUrl": "https://jobs.lever.co/examplelever/lev-2",
                    "categories": {"location": "Berlin"},
                    "descriptionPlain": "Marketing role.",
                },
                {
                    "id": "lev-3",
                    "text": "Backend Engineer",
                    "hostedUrl": "https://jobs.lever.co/examplelever/lev-3",
                    "categories": {"location": "Remote - US only"},
                    "descriptionPlain": "Python APIs.",
                },
                {
                    "id": "lev-4",
                    "text": "Backend Engineer",
                    "hostedUrl": "https://jobs.lever.co/examplelever/lev-4",
                    "categories": {"location": "Berlin"},
                    "descriptionPlain": "Python APIs. German C1 is required.",
                },
            ],
            ashby_url: {
                "jobs": [
                    {
                        "id": "ash-1",
                        "title": "Applied AI Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/exampleashby/ash-1",
                        "location": "Hamburg",
                        "descriptionHtml": "<p>LLM and API integration with Python.</p>",
                        "publishedAt": "2026-05-21T12:00:00Z",
                        "compensation": {
                            "salaryRange": {
                                "min": 60000,
                                "max": 80000,
                                "currencyCode": "EUR",
                            }
                        },
                    }
                ]
            },
        },
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    jobs = [item["json"] for item in payload["result"]]

    assert [job["source"] for job in jobs] == [
        "ats_watchlist:greenhouse",
        "ats_watchlist:lever",
        "ats_watchlist:ashby",
    ]
    assert [job["company"] for job in jobs] == ["Green Co", "Lever Co", "Ashby Co"]
    assert jobs[0]["remote"] is True
    assert jobs[0]["likely_english"] is True
    assert jobs[1]["url"] == "https://jobs.lever.co/examplelever/lev-1"
    assert jobs[2]["salary_min"] == 60000
    assert jobs[2]["salary_max"] == 80000
    assert jobs[2]["salary_currency"] == "EUR"
    assert jobs[0]["_crawlMeta"]["total_results"] == 3
    assert jobs[0]["_crawlMeta"]["companies_succeeded"] == 3
    assert payload["requests"] == [greenhouse_url, lever_url, ashby_url]
    assert (project_dir / "temp" / "ats-watchlist-state.json").is_file()


def test_ats_watchlist_poll_guard_skips_recent_completed_run(tmp_path):
    greenhouse_url = "https://boards-api.greenhouse.io/v1/boards/examplegreen/jobs?content=true"
    project_dir = make_project(
        tmp_path,
        [{"company": "Green Co", "provider": "greenhouse", "slug": "examplegreen"}],
    )
    write_json(
        project_dir / "temp" / "ats-watchlist-state.json",
        {"last_completed_at": datetime.now(timezone.utc).isoformat()},
    )

    result = run_ats_fetch(project_dir, responses={greenhouse_url: {"jobs": []}})

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["requests"] == []
    assert payload["result"] == [
        {
            "json": {
                "_empty": True,
                "_crawlMeta": {
                    "source": "ats_watchlist",
                    "skipped_by_interval": True,
                },
            }
        }
    ]


def test_ats_watchlist_records_company_errors_without_killing_successful_run(tmp_path):
    greenhouse_url = "https://boards-api.greenhouse.io/v1/boards/examplegreen/jobs?content=true"
    lever_url = "https://api.lever.co/v0/postings/brokenlever?mode=json"
    project_dir = make_project(
        tmp_path,
        [
            {"company": "Green Co", "provider": "greenhouse", "slug": "examplegreen"},
            {"company": "Broken Lever", "provider": "lever", "slug": "brokenlever"},
        ],
    )

    result = run_ats_fetch(
        project_dir,
        responses={
            greenhouse_url: {
                "jobs": [
                    {
                        "id": 111,
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/examplegreen/jobs/111",
                        "location": {"name": "Berlin"},
                        "content": "Join the team and build Python APIs.",
                    }
                ]
            }
        },
        failures=[lever_url],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    jobs = [item["json"] for item in payload["result"]]

    assert len(jobs) == 1
    assert jobs[0]["_crawlMeta"]["companies_succeeded"] == 1
    assert jobs[0]["_crawlMeta"]["fetch_errors"] == 1
    assert jobs[0]["_crawlMeta"]["errors"][0]["company"] == "Broken Lever"
    assert jobs[0]["_crawlMeta"]["errors"][0]["provider"] == "lever"


def test_ats_watchlist_throws_when_every_enabled_company_fails(tmp_path):
    lever_url = "https://api.lever.co/v0/postings/brokenlever?mode=json"
    project_dir = make_project(
        tmp_path,
        [{"company": "Broken Lever", "provider": "lever", "slug": "brokenlever"}],
    )

    result = run_ats_fetch(project_dir, failures=[lever_url])

    assert result.returncode == 1
    assert "ATS Watchlist: every enabled company failed" in result.stderr
