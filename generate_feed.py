#!/usr/bin/env python3
"""Compatibility entrypoint: regenerate derived files from public/archive.

Alba / local habit: after appending to public/archive/YYYY-MM-DD.json, run:
  python3 generate_feed.py

Single source of truth is public/archive/. scripts/sync_root_pages.py
refreshes a legacy root mirror only when .no-root-mirror is absent, and never
overwrites README.md. Pages Source is GitHub Actions and deploys public/ only.
"""
from scripts.generate_derived import main as derive
from scripts.sync_root_pages import main as sync_root

if __name__ == "__main__":
    derive()
    sync_root()
