#!/usr/bin/env python3
"""INTERIM: mirror public/ → repo root for legacy GitHub Pages (branch /).

Remove this once .github/workflows/deploy-pages.yml is installed (needs gh
token with `workflow` scope) and Pages source is set to GitHub Actions.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
FILES = [
    "index.html", "items.json", "feed.xml", "tools-radar.html", "tools-radar.json",
    "today3.txt", "theses.json", "source-scores.json", "owner-actions.json", ".nojekyll",
    "README.md",
]
DIRS = ["archive", "feeds", "config", "memos"]


def main() -> None:
    for name in FILES:
        src = PUBLIC / name
        if src.exists():
            shutil.copy2(src, ROOT / name)
    for rel in DIRS:
        src = PUBLIC / rel
        dst = ROOT / rel
        if not src.is_dir():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    print("synced public/ → repo root (interim legacy Pages)")


if __name__ == "__main__":
    main()
