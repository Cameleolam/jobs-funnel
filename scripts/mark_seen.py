#!/usr/bin/env python3
"""Add a URL to the seen-urls cache.

Usage:
    python mark_seen.py <project_dir> <url>
"""

import json
import msvcrt
import os
import sys
import time


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    project_dir = sys.argv[1]
    url = sys.argv[2]
    cache_file = os.path.join(project_dir, "output", "_seen_urls.json")
    lock_file = cache_file + ".lock"

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    # Acquire file lock to prevent concurrent overwrites
    for _ in range(50):
        try:
            lf = open(lock_file, "x")
            break
        except FileExistsError:
            time.sleep(0.1)
    else:
        # Stale lock — force acquire
        lf = open(lock_file, "w")

    try:
        urls = []
        try:
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    urls = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

        if url not in urls:
            urls.append(url)

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(urls, f, indent=2)

        print("ok")
    finally:
        lf.close()
        try:
            os.remove(lock_file)
        except OSError:
            pass


if __name__ == "__main__":
    main()
