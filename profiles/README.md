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

1. Copy an existing profile directory:
   ```bash
   cp -r profiles/profile1 profiles/myprofile
   ```

2. Edit `search.json` - set your search terms and location:
   - `aa_searches`: Job title queries for Arbeitsagentur API (server-side search)
   - `aa_location`: City name for Arbeitsagentur (e.g., "Hamburg", "Berlin")
   - `aa_radius_km`: Search radius in km
   - `an_title_keywords`: Title keywords for Arbeitnow client-side filtering
   - `an_tag_keywords`: Tech/skill tags to match
   - `an_location_keywords`: Location keywords to match
   - `an_negative_keywords`: Job titles to auto-skip (e.g., "manager", "consultant")

3. Edit `filter_prompt.md` - this is the full candidate profile that Claude uses to score jobs. Include:
   - Target roles, location preference, visa status
   - Core tech stack and experience level
   - Honest gaps (what you DON'T know)
   - Hard blockers (language requirements, seniority, etc.)
   - Scoring rubric with examples
   - CV variant selection rules

4. Edit `generate_prompt.md` - your work history for CV/cover letter tailoring (optional, only needed if using the generate workflow).

5. Replace CV HTML files in `cvs/` with your own variants.

6. Set up your `.env`:
   ```
   JOBS_FUNNEL_PROFILE=myprofile
   JOBS_FUNNEL_TABLE=jobs_myprofile
   JOBS_FUNNEL_SHEET_ID=<your Google Sheet ID>
   ```

7. Create your database table:
   ```sql
   -- Edit setup_db.sql: replace "jobs" with "jobs_myprofile", then run:
   psql -U postgres -d jobs_funnel -f scripts/setup_db.sql
   ```

8. Create a "Tracker" and "Metrics" tab in your Google Sheet with the expected column headers.

## Switching profiles

Change `JOBS_FUNNEL_PROFILE`, `JOBS_FUNNEL_TABLE`, and `JOBS_FUNNEL_SHEET_ID` in your `.env` file, then restart n8n.

## Notes

- Profiles are gitignored (they contain personal data like CVs and contact info)
- The pipeline code is profile-agnostic - it reads everything from the active profile directory
- Each profile should use its own database table and Google Sheet to avoid mixing data
