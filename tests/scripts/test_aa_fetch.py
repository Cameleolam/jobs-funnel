import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_project(tmp_path: Path):
    write_json(
        tmp_path / "config.json",
        {
            "aa_max_pages": 1,
            "aa_max_fetches": 10,
            "aa_fetch_delay_ms": 0,
            "aa_fetch_timeout_ms": 1000,
            "description_max_chars": 5000,
            "api_max_retries": 0,
            "api_retry_delay_ms": 0,
            "circuit_breaker_threshold": 0.8,
            "circuit_breaker_min_requests": 5,
        },
    )
    write_json(
        tmp_path / "profiles" / "profile1" / "search.json",
        {
            "country": "de",
            "aa_searches": ["UI Designer"],
            "aa_locations": [{"location": "Hamburg", "radius_km": 200}],
        },
    )
    write_json(tmp_path / "countries" / "de" / "staffing_patterns.json", {"patterns": ["Recruiting"]})
    write_json(tmp_path / "countries" / "de" / "geo_allowlist.json", {"allowlist": ["hamburg"]})
    write_json(
        tmp_path / "countries" / "de" / "language_hints.json",
        {
            "languages": {
                "en": {
                    "stopwords": ["the", "and", "team"],
                    "threshold": 2,
                    "sample_chars": 500,
                }
            }
        },
    )
    return tmp_path


def run_node(script_name: str, payload):
    harness = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const code = fs.readFileSync(input.script, 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const args = input.script.endsWith('aa-fetch-desc.js')
  ? ['$input', '$env', 'require', 'setTimeout', 'Buffer', code]
  : ['$env', 'require', 'setTimeout', code];
const fn = new AsyncFunction(...args);
const requests = [];
const context = {
  helpers: {
    httpRequest: async (opts) => {
      requests.push(opts);
      if (!(opts.url in input.responses)) throw new Error(`missing fake response for ${opts.url}`);
      return input.responses[opts.url];
    }
  }
};
function immediateTimeout(callback) { callback(); return 0; }
const env = { JOBS_FUNNEL_PROJECT_DIR: input.projectDir, JOBS_FUNNEL_PROFILE: 'profile1' };
const callArgs = input.script.endsWith('aa-fetch-desc.js')
  ? [{ all: () => input.items }, env, require, immediateTimeout, Buffer]
  : [env, require, immediateTimeout];
Promise.resolve(fn.call(context, ...callArgs)).then(
  result => process.stdout.write(JSON.stringify({ result, requests })),
  error => { console.error(error && error.stack ? error.stack : String(error)); process.exit(1); }
);
"""
    return subprocess.run(
        ["node", "-e", harness],
        cwd=REPO,
        input=json.dumps({"script": f"scripts/n8n/{script_name}", **payload}),
        capture_output=True,
        text=True,
    )


def test_aa_search_uses_v6_and_normalizes_results(tmp_path):
    project_dir = make_project(tmp_path)
    url = (
        "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
        "?was=UI%20Designer&wo=Hamburg&umkreis=200&veroeffentlichtseit=30"
        "&pav=false&zeitarbeit=false&size=100&page=1"
    )
    response = {
        "ergebnisliste": [
            {
                "referenznummer": "16106-123-S",
                "stellenangebotsTitel": "UX/UI Designer (m/w/d)",
                "firma": "Example GmbH",
                "hauptberuf": "UX-Designer/in",
                "stellenlokationen": [
                    {"adresse": {"ort": "Hamburg", "region": "HAMBURG"}}
                ],
                "eintrittszeitraum": {"von": "2026-09-01"},
                "datumErsteVeroeffentlichung": "2026-08-27",
            }
        ],
        "maxErgebnisse": 1,
    }

    result = run_node(
        "aa-fetch.js",
        {"projectDir": str(project_dir), "responses": {url: response}},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job = payload["result"][0]["json"]
    assert payload["requests"][0]["url"] == url
    assert payload["requests"][0]["headers"]["X-API-Key"] == "jobboerse-jobsuche"
    assert job["external_id"] == "16106-123-S"
    assert job["title"] == "UX/UI Designer (m/w/d)"
    assert job["company"] == "Example GmbH"
    assert job["location"] == "Hamburg"
    assert job["start_date"] == "2026-09-01"
    assert job["posted_at"] == "2026-08-27"
    assert job["url"].endswith("id=16106-123-S")


def test_aa_description_fetch_uses_jobdetails_endpoint(tmp_path):
    project_dir = make_project(tmp_path)
    detail_url = (
        "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
        "MTYxMDYtMTIzLVM="
    )
    items = [
        {
            "json": {
                "source": "arbeitsagentur",
                "external_id": "16106-123-S",
                "title": "UX/UI Designer",
                "company": "Example GmbH",
                "location": "Hamburg",
                "description": "Fallback description",
                "description_quality": "empty",
                "_rawApiData": {"referenznummer": "16106-123-S"},
            }
        }
    ]
    detail = {
        "referenznummer": "16106-123-S",
        "stellenangebotsBeschreibung": (
            "Join the design team. Your responsibilities include user research, "
            "accessibility testing, interaction design, and working with developers. "
            "The role requires experience with prototypes and usability studies. "
            "You will collaborate with the product team and document design decisions."
        ),
    }

    result = run_node(
        "aa-fetch-desc.js",
        {
            "projectDir": str(project_dir),
            "items": items,
            "responses": {detail_url: detail},
        },
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job = payload["result"][0]["json"]
    assert payload["requests"][0]["url"] == detail_url
    assert payload["requests"][0]["headers"]["X-API-Key"] == "jobboerse-jobsuche"
    assert job["description"].startswith("Join the design team")
    assert job["description_quality"] == "good"
    assert job["_rawApiData"]["_jobDetails"]["referenznummer"] == "16106-123-S"
