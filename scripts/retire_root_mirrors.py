#!/usr/bin/env python3
"""Delete repo-root Pages mirrors after Pages source is GitHub Actions.

Does not run unless --i-switched-pages-to-actions is passed.
Leaves README.md, config.json, public/, and docs untouched.
Writes .no-root-mirror so generate_feed.py / sync_root_pages.py stop recreating them.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".no-root-mirror"
FILES = [
    "index.html",
    "items.json",
    "feed.xml",
    "tools-radar.html",
    "tools-radar.json",
    "today3.txt",
    "theses.json",
    "source-scores.json",
    "owner-actions.json",
    "practice.html",
    "week.html",
    "subscribe.html",
    "agent.html",
    "about.html",
    "practice.json",
    "practice.sample.json",
]
DIRS = ["archive", "feeds", "memos", "config", "assets", "practice"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--i-switched-pages-to-actions",
        action="store_true",
        help="Confirm Settings → Pages → Source is GitHub Actions and a deploy of public/ succeeded",
    )
    args = ap.parse_args()
    if not args.i_switched_pages_to_actions:
        print(
            "refusing: pass --i-switched-pages-to-actions after the live site is served from public/.\n"
            "Until then, root mirrors keep legacy Pages (main /) from 404ing.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    for name in FILES:
        path = ROOT / name
        if path.is_file():
            path.unlink()
            print(f"removed {name}")
    for rel in DIRS:
        path = ROOT / rel
        if path.is_dir():
            shutil.rmtree(path)
            print(f"removed {rel}/")
    MARKER.write_text(
        "Root Pages mirrors retired. GitHub Pages deploys public/ via Actions.\n",
        encoding="utf-8",
    )
    print("wrote .no-root-mirror")
    print("next: git add -A && git commit && git push  (do not commit public/ secrets)")


if __name__ == "__main__":
    main()
