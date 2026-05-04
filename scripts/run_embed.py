#!/usr/bin/env python3
"""n8n-friendly wrapper for scripts/embed.py --job-id.

Usage (from n8n ExecuteCommand):
    python scripts/run_embed.py <project_dir> <job_id>

Why this exists: matches the pattern of scripts/run_filter.py — keeps the
n8n command line simple and absorbs path/quoting quirks here.
"""
import os
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print('{"status":"error","error":"Usage: run_embed.py <project_dir> <job_id>"}')
        sys.exit(1)
    project_dir = Path(sys.argv[1]).resolve()
    job_id = sys.argv[2]
    embed_py = project_dir / "scripts" / "embed.py"
    env = {**os.environ, "PYTHONPATH": str(project_dir)}
    rc = subprocess.call(
        [sys.executable, str(embed_py), "--job-id", job_id],
        cwd=str(project_dir),
        env=env,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
