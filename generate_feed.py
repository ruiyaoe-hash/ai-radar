#!/usr/bin/env python3
"""Compatibility entrypoint: regenerate derived files from public/archive.

Alba / local habit: after appending to public/archive/YYYY-MM-DD.json, run:
  python3 generate_feed.py

Single source of truth is public/archive/. Root mirrors and data/ are retired;
GitHub Pages deploys from public/ via Actions.
"""
from scripts.generate_derived import main

if __name__ == "__main__":
    main()
