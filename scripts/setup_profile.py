"""Create a new profile from the template.

Usage:
    python scripts/setup_profile.py <profile_name>

Copies templates/profile/ into profiles/<profile_name>/ and prints next steps.
"""

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = PROJECT_DIR / "templates" / "profile"
PROFILES_DIR = PROJECT_DIR / "profiles"


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python scripts/setup_profile.py <profile_name>")
        print("Example: python scripts/setup_profile.py myprofile")
        sys.exit(1)

    name = sys.argv[1].strip()
    if not name or "/" in name or "\\" in name:
        print(f"Error: invalid profile name: {name!r}")
        sys.exit(1)

    target = PROFILES_DIR / name
    if target.exists():
        print(f"Error: {target} already exists. Remove it first or choose another name.")
        sys.exit(1)

    if not TEMPLATE_DIR.exists():
        print(f"Error: template not found at {TEMPLATE_DIR}")
        sys.exit(1)

    shutil.copytree(TEMPLATE_DIR, target)
    print(f"Created profile at: {target}")
    print()
    print("Next steps:")
    print(f"  1. Edit {target / 'search.json'} with your search terms and locations")
    print(f"  2. Edit {target / 'filter_prompt.md'} with your candidate profile and scoring rubric")
    print(f"  3. (Optional) Edit {target / 'generate_prompt.md'} if using CV/cover letter generation")
    print(f"  4. (Optional) Create {target / 'cvs/'} with your CV variants as HTML files")
    print(f"  5. Set environment variables in .env:")
    print(f"       JOBS_FUNNEL_PROFILE={name}")
    print(f"       JOBS_FUNNEL_TABLE=jobs_{name}")
    print(f"  6. Create the database table:")
    print(f"       psql -U postgres -d jobs_funnel -f scripts/setup_db.sql")
    print(f"  7. Validate your profile:")
    print(f"       python scripts/validate_profile.py profiles/{name}/")


if __name__ == "__main__":
    main()
