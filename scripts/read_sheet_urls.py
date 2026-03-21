#!/usr/bin/env python3
"""Print all previously-processed URLs as a JSON array.
Reads from a local cache file that gets appended after each run.

Usage:
    python read_sheet_urls.py <project_dir>
"""

import json
import os
import sys


def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_file = os.path.join(project_dir, "output", "_seen_urls.json")

    urls = []
    try:
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                urls = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

    print(json.dumps(urls))


if __name__ == "__main__":
    main()
