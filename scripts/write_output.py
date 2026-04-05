#!/usr/bin/env python3
"""NOTE: Not part of the active pipeline. Kept for future use.

Write generated CV/cover letter files to local output directory.

Usage:
    python write_output.py <json_file_path>

Output: JSON with outputDir and folderName on stdout
"""

import base64
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PIPELINE_DIR / "output"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No input provided"}))
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        # Try parsing as inline JSON (backwards compat)
        try:
            job = json.loads(sys.argv[1])
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"File not found and invalid JSON: {e}"}))
            sys.exit(1)
    else:
        try:
            job = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON in file: {e}"}))
            sys.exit(1)

    company = re.sub(r'[^a-zA-Z0-9]', '_', job.get("company", "unknown"))[:30]
    from datetime import date
    today = date.today().isoformat()
    dir_path = OUTPUT_DIR / f"{today}_{company}"
    dir_path.mkdir(parents=True, exist_ok=True)

    # Write CV
    (dir_path / "cv.html").write_text(job.get("tailored_cv_html", ""), encoding="utf-8")

    # Write cover letter
    cl_html = job.get("cover_letter_html", "")
    cl_text = job.get("cover_letter_text", "")
    if not cl_html:
        cl_html = f"<html><body><pre>{cl_text}</pre></body></html>"
    (dir_path / "cover_letter.html").write_text(cl_html, encoding="utf-8")
    (dir_path / "cover_letter.txt").write_text(cl_text, encoding="utf-8")

    # Write assessment
    (dir_path / "assessment.json").write_text(
        json.dumps(job.get("assessment", {}), indent=2), encoding="utf-8"
    )

    # Write job info
    (dir_path / "job.json").write_text(json.dumps({
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "url": job.get("url", ""),
        "description": job.get("description", ""),
    }, indent=2), encoding="utf-8")

    folder_name = f"{today} {job.get('company', 'Unknown')} - {job.get('title', 'Role')}"

    # Base64-encode each file for downstream binary conversion (n8n sandbox can't use fs)
    files_b64 = {}
    for fname in ["cv.html", "cover_letter.html", "cover_letter.txt", "assessment.json", "job.json"]:
        fpath = dir_path / fname
        if fpath.exists():
            files_b64[fname] = base64.b64encode(fpath.read_bytes()).decode("ascii")

    print(json.dumps({
        "outputDir": str(dir_path).replace("\\", "/"),
        "folderName": folder_name,
        "files": files_b64,
    }))


if __name__ == "__main__":
    main()
