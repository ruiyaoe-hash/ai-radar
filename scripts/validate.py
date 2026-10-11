#!/usr/bin/env python3
"""CI validators: schema, archive monotonicity, feed count == items."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"

LENSES = {"工具", "赛道", "模式", "时机"}
STATUSES = {"rumor", "multi_source", "confirmed"}
ID_RE = re.compile(r"^evt-[0-9]{8}-[a-z0-9][a-z0-9-]{0,80}$")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def validate_card(it: dict, path: str) -> None:
    if it.get("schema_version") != 2:
        fail(f"{path}: schema_version must be 2")
    eid = it.get("id") or ""
    if not ID_RE.match(eid):
        fail(f"{path}: bad id {eid!r}")
    if it.get("status") not in STATUSES:
        fail(f"{path}: bad status")
    if it.get("lens") not in LENSES:
        fail(f"{path}: bad lens {it.get('lens')!r}")
    if it.get("priority") not in {"P0", "P1"}:
        fail(f"{path}: bad priority")
    if not it.get("title"):
        fail(f"{path}: missing title")
    if not it.get("date"):
        fail(f"{path}: missing date")
    obj = it.get("objective")
    if not isinstance(obj, list) or not obj:
        fail(f"{path}: objective required")
    if "bullets" in it:
        fail(f"{path}: bullets must be dropped")
    sources = it.get("sources")
    if not isinstance(sources, list) or not sources:
        fail(f"{path}: sources[] required")
    for s in sources:
        if not s.get("url") or not s.get("handle") or s.get("role") not in {
            "primary", "analysis", "report"
        }:
            fail(f"{path}: bad source entry {s!r}")
    so = it.get("so_what")
    if so is not None:
        if not isinstance(so, dict) or not (so.get("falsifier") or "").strip():
            fail(f"{path}: so_what requires non-empty falsifier")


def check_schema() -> int:
    n = 0
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("date") != path.stem:
            fail(f"{path.name}: date field != filename")
        items = data.get("items") or []
        if data.get("count") != len(items):
            fail(f"{path.name}: count != len(items)")
        for it in items:
            validate_card(it, f"{path.name}:{it.get('id')}")
            n += 1
    print(f"OK schema: {n} cards")
    return n


def list_archive_dates() -> set[str]:
    return {p.stem for p in ARCHIVE.glob("????-??-??.json")}


def check_monotonic() -> None:
    ids: set[str] = set()
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            eid = it["id"]
            if eid in ids:
                fail(f"duplicate id {eid}")
            ids.add(eid)

    # Against origin/main (or BASE_SHA) if we can read it
    base_ref = os.environ.get("VALIDATE_BASE_REF", "origin/main")
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", base_ref, "public/archive/"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        old = set()
        for line in out.splitlines():
            name = Path(line).name
            if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", name):
                old.add(name[:-5])
        new = list_archive_dates()
        removed = old - new
        if removed:
            fail(f"archive dates removed (not monotonic): {sorted(removed)}")
        print(f"OK monotonic vs {base_ref}: +{len(new - old)} days, 0 removed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("OK monotonic local (no base ref comparable)")


def check_feed() -> None:
    items_path = PUBLIC / "items.json"
    feed_path = PUBLIC / "feed.xml"
    if not items_path.exists() or not feed_path.exists():
        fail("items.json or feed.xml missing — run generate_derived.py first")
    data = json.loads(items_path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    tree = ET.parse(feed_path)
    channel = tree.getroot().find("channel")
    rss_items = channel.findall("item") if channel is not None else []
    ni, nr = len(items), len(rss_items)
    if ni != nr:
        fail(f"feed item count {nr} != items.json {ni}")
    print(f"OK feed: {nr} items match board")


def main() -> None:
    check_schema()
    check_monotonic()
    check_feed()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
