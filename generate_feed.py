#!/usr/bin/env python3
"""Compatibility entrypoint: regenerate derived files from public/archive.

Alba / local habit: after appending to public/archive/YYYY-MM-DD.json, run:
  python3 generate_feed.py

Single source of truth is public/archive/. This also refreshes the legacy
root mirror (GitHub Pages is still branch main /) and never overwrites README.md.
After Pages is switched to Actions, retire_root_mirrors.py stops the mirror.
"""
from scripts.generate_derived import main as derive
from scripts.sync_root_pages import main as sync_root

if __name__ == "__main__":
    derive()
    sync_root()
