#!/usr/bin/env python3
"""INTERIM: mirror public/ → repo root for legacy GitHub Pages (branch main /).

Stop once Pages source is GitHub Actions and scripts/retire_root_mirrors.py
has written .no-root-mirror. Never copies README.md (repo docs, not the site).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
MARKER = ROOT / ".no-root-mirror"
FILES = [
    "index.html", "items.json", "feed.xml", "tools-radar.html", "tools-radar.json",
    "today3.txt", "theses.json", "source-scores.json", "owner-actions.json", ".nojekyll",
    "practice.html", "week.html", "subscribe.html", "agent.html", "about.html",
    "practice.json", "practice.sample.json",
]
DIRS = ["archive", "feeds", "config", "memos", "assets", "practice"]


def main() -> None:
    if MARKER.exists() and os.environ.get("FORCE_ROOT_MIRROR") != "1":
        print("root mirror retired (.no-root-mirror present); skip sync", file=sys.stderr)
        return
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
