# Profiles

Each profile represents a job seeker with their own search terms, scoring rubric, CV variants, and prompts.

## Directory structure

```
profiles/
├── profile1/
│   ├── search.json          # Search terms, location, keyword filters
│   ├── filter_prompt.md     # Candidate profile + scoring rubric for Claude
│   ├── generate_prompt.md   # Work history + CV/cover letter tailoring rules
│   └── cvs/                 # CV variants (HTML files)
│       ├── software.html
│       └── ...
└── README.md                # This file
```

## Creating a new profile

1. Run the setup script:
   ```bash
   python scripts/setup_profile.py myprofile
   ```
   This copies the template from `templates/profile/` into `profiles/myprofile/`.

2. Edit `search.json` - set your search terms and location:
   - `aa_searches`: Job title queries for Arbeitsagentur API (server-side search)
   - `aa_location`: City name for Arbeitsagentur (e.g., "Hamburg", "Berlin")
   - `aa_radius_km`: Search radius in km
   - `an_title_keywords`: Title keywords for Arbeitnow client-side filtering
   - `an_tag_keywords`: Tech/skill tags to match
   - `an_location_keywords`: Location keywords to match
   - `an_negative_keywords`: Job titles to auto-skip (e.g., "manager", "consultant")

3. Edit `filter_prompt.md` - this is the full candidate profile that Claude uses to score jobs. The template includes a fictional example; replace it with your own profile. The prompt structure is fully customizable - adapt it to your background or refine it with AI. Key sections to fill in:
   - Target roles, location preference, visa status
   - Core tech stack and experience level
   - Honest gaps (what you DON'T know)
   - Hard blockers (language requirements, seniority, etc.)
   - Scoring rubric with examples
   - CV variant selection rules (match the names of your HTML files in cvs/)

4. Edit `generate_prompt.md` - your work history for CV/cover letter tailoring (optional, only needed if using the generate workflow).

5. (Optional) Create a `cvs/` directory with your CV variants as HTML files. CV generation is not part of the active workflow, but the variant names are used as labels during scoring.

6. Set up your `.env`:
   ```
   JOBS_FUNNEL_PROFILE=myprofile
   JOBS_FUNNEL_TABLE=jobs_myprofile
   ```

7. Create your database table:
   ```sql
   -- Edit setup_db.sql: replace "jobs" with "jobs_myprofile", then run:
   psql -U postgres -d jobs_funnel -f scripts/setup_db.sql
   ```

## Switching profiles

Change `JOBS_FUNNEL_PROFILE` and `JOBS_FUNNEL_TABLE` in your `.env` file, then restart n8n.

## Validating a profile

Run the validation script to check your profile for common issues:

```bash
python scripts/validate_profile.py profiles/myprofile/
```

This checks:
- `search.json` exists with all required keys and correct types
- `filter_prompt.md` exists and is non-empty
- `cvs/` directory (optional, warns if missing)
- `generate_prompt.md` exists (optional, warns if missing)

Use `--strict` to treat warnings as errors:

```bash
python scripts/validate_profile.py profiles/myprofile/ --strict
```

## Notes

- Profiles are gitignored (they contain personal data like CVs and contact info)
- The pipeline code is profile-agnostic - it reads everything from the active profile directory
- Each profile should use its own database table to avoid mixing data
