#!/usr/bin/env python3
"""CI validators: JSON Schema, archive monotonicity, feed well-formed + counts.

  pip install -r requirements-ci.txt
  python3 scripts/generate_derived.py && python3 scripts/validate.py

Base for the monotonic check:
  VALIDATE_BASE_SHA   (preferred; CI sets the PR base or github.event.before)
  VALIDATE_BASE_REF   (default origin/main when no SHA is set)
All-zero SHAs and a missing base are skipped with a notice. An explicit SHA
that cannot be read fails the job.
"""
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
SCHEMAS = ROOT / "schemas"

LENSES = {"工具", "赛道", "模式", "时机"}
LENS_FEEDS = {
    "工具": "lens-tools.xml",
    "赛道": "lens-tracks.xml",
    "模式": "lens-models.xml",
    "时机": "lens-timing.xml",
}
STATUSES = {"rumor", "multi_source", "confirmed"}
ID_RE = re.compile(r"^evt-[0-9]{8}-[a-z0-9][a-z0-9-]{0,80}$")
# Recommended on new cards. Legacy archive cards omit them and still validate.
OPTIONAL_CARD_TIMES = ("published_at", "ingested_at")
UTC_STAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|\+00:00)$"
)
ZERO_SHA = "0" * 40
ATOM = "{http://www.w3.org/2005/Atom}"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_validators():
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")

    card = json.loads((SCHEMAS / "card.schema.json").read_text(encoding="utf-8"))
    day = json.loads((SCHEMAS / "archive-day.schema.json").read_text(encoding="utf-8"))
    card_res = Resource(contents=card, specification=DRAFT202012)
    registry = Registry().with_resources(
        [
            (card.get("$id") or "", card_res),
            ("card.schema.json", card_res),
            (
                "https://ruiyaoe-hash.github.io/ai-radar/schemas/card.schema.json",
                card_res,
            ),
        ]
    )
    return (
        Draft202012Validator(card, registry=registry),
        Draft202012Validator(day, registry=registry),
    )


def validate_card(it: dict, path: str, card_validator) -> None:
    errors = sorted(card_validator.iter_errors(it), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "(root)"
        fail(f"{path}: schema {loc}: {first.message}")
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
            "primary",
            "analysis",
            "report",
        }:
            fail(f"{path}: bad source entry {s!r}")
    so = it.get("so_what")
    if so is not None:
        if not isinstance(so, dict) or not (so.get("falsifier") or "").strip():
            fail(f"{path}: so_what requires non-empty falsifier")
    for key in OPTIONAL_CARD_TIMES:
        val = it.get(key)
        if val is None:
            continue
        if not isinstance(val, str) or not UTC_STAMP.match(val):
            fail(f"{path}: {key} must be ISO-8601 UTC, got {val!r}")
    # rumor may stay priority P0; the board renders that as 市场信号, never as 今日必看.


def check_schema() -> int:
    card_validator, day_validator = load_validators()
    n = 0
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        day_errors = sorted(day_validator.iter_errors(data), key=lambda e: list(e.path))
        if day_errors:
            first = day_errors[0]
            loc = "/".join(str(p) for p in first.path) or "(root)"
            fail(f"{path.name}: day schema {loc}: {first.message}")
        if data.get("date") != path.stem:
            fail(f"{path.name}: date field != filename")
        items = data.get("items") or []
        if data.get("count") != len(items):
            fail(f"{path.name}: count != len(items)")
        for it in items:
            validate_card(it, f"{path.name}:{it.get('id')}", card_validator)
            n += 1
    print(f"OK schema: {n} cards (schemas/card.schema.json + archive-day.schema.json)")
    return n


def list_archive_dates() -> set[str]:
    return {p.stem for p in ARCHIVE.glob("????-??-??.json")}


def item_key(it: dict) -> str:
    if it.get("id"):
        return "id:" + str(it["id"])
    if it.get("url"):
        return "url:" + str(it["url"])
    return "title:" + str(it.get("title") or "")


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None


def resolve_base() -> str | None:
    sha = (os.environ.get("VALIDATE_BASE_SHA") or "").strip()
    if sha and sha != ZERO_SHA and set(sha) != {"0"}:
        return sha
    ref = (os.environ.get("VALIDATE_BASE_REF") or "").strip()
    if not ref and not sha:
        ref = "origin/main"
    if not ref:
        return None
    try:
        resolved = subprocess.check_output(
            ["git", "rev-parse", "--verify", ref],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if resolved == head:
        # Comparing a commit to itself cannot see deletions inside that commit.
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if parent.returncode == 0:
            return parent.stdout.strip()
    return resolved


def check_monotonic() -> None:
    ids: set[str] = set()
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            eid = it["id"]
            if eid in ids:
                fail(f"duplicate id {eid}")
            ids.add(eid)

    base = resolve_base()
    if not base:
        print("OK monotonic local (no base ref comparable)")
        return

    probe = git_show(base, "public/archive/index.json")
    if probe is None and git_show(base, "README.md") is None:
        explicit = (os.environ.get("VALIDATE_BASE_SHA") or "").strip()
        if explicit and explicit != ZERO_SHA:
            fail(f"cannot read base {base} (fetch the base commit before validate)")
        print("OK monotonic local (base tree unreadable)")
        return

    old_dates: set[str] = set()
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", base, "public/archive/"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if listing.returncode != 0:
        fail(f"git ls-tree failed for {base}: {listing.stderr.strip()}")
    for line in listing.stdout.splitlines():
        name = Path(line).name
        if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", name):
            old_dates.add(name[:-5])

    new_dates = list_archive_dates()
    removed_days = old_dates - new_dates
    if removed_days:
        fail(f"archive dates removed (not monotonic): {sorted(removed_days)}")

    removed_keys: list[str] = []
    shrunk: list[str] = []
    for date in sorted(old_dates):
        raw = git_show(base, f"public/archive/{date}.json")
        if raw is None:
            fail(f"missing base archive blob public/archive/{date}.json @ {base}")
        old = json.loads(raw)
        new = json.loads((ARCHIVE / f"{date}.json").read_text(encoding="utf-8"))
        old_items = old.get("items") or []
        new_items = new.get("items") or []
        if len(new_items) < len(old_items):
            shrunk.append(f"{date} {len(old_items)}→{len(new_items)}")
        new_keys = {item_key(it) for it in new_items}
        for it in old_items:
            key = item_key(it)
            if key not in new_keys:
                removed_keys.append(f"{date}:{key}")
    if shrunk:
        fail("archive day counts decreased: " + ", ".join(shrunk))
    if removed_keys:
        fail("archive cards removed: " + ", ".join(removed_keys[:20]))

    print(
        f"OK monotonic vs {base[:12]}: +{len(new_dates - old_dates)} days, "
        f"0 days removed, 0 cards removed"
    )


def parse_feed(path: Path) -> list[ET.Element]:
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        fail(f"{path.name}: not well-formed XML: {e}")
    root = tree.getroot()
    if root.tag != "rss":
        fail(f"{path.name}: root is {root.tag}, expected rss")
    channel = root.find("channel")
    if channel is None:
        fail(f"{path.name}: missing channel")
    if channel.find(f"{ATOM}link") is None and channel.find("link") is None:
        fail(f"{path.name}: missing link")
    return channel.findall("item")


def check_feed() -> None:
    items_path = PUBLIC / "items.json"
    feed_path = PUBLIC / "feed.xml"
    if not items_path.exists() or not feed_path.exists():
        fail("items.json or feed.xml missing — run generate_derived.py first")
    data = json.loads(items_path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    rss_items = parse_feed(feed_path)
    ni, nr = len(items), len(rss_items)
    if ni != nr:
        fail(f"feed item count {nr} != items.json {ni}")
    for el in rss_items:
        for child in ("title", "link", "guid", "pubDate"):
            node = el.find(child)
            if node is None or not (node.text or "").strip():
                fail(f"feed.xml item missing {child}")
    print(f"OK feed: {nr} items match board, well-formed")

    for lens, name in LENS_FEEDS.items():
        path = PUBLIC / "feeds" / name
        if not path.exists():
            fail(f"missing {path.relative_to(PUBLIC)}")
        got = len(parse_feed(path))
        expect = sum(1 for it in items if it.get("lens") == lens)
        if got != expect:
            fail(f"{name}: {got} items != board lens {lens!r} count {expect}")
    print("OK lens feeds: counts match items.json")


def check_practice() -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((SCHEMAS / "practice.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for rel in ("public/practice.json", "public/practice.sample.json"):
        path = ROOT / rel
        if not path.exists():
            fail(f"missing {rel}")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            loc = "/".join(str(p) for p in first.path) or "(root)"
            fail(f"{rel}: schema {loc}: {first.message}")
    live = json.loads((PUBLIC / "practice.json").read_text(encoding="utf-8"))
    sample_ids = {
        it.get("id")
        for it in json.loads((PUBLIC / "practice.sample.json").read_text(encoding="utf-8")).get("items") or []
    }
    leaked = [it.get("id") for it in live.get("items") or [] if it.get("sample") or it.get("id") in sample_ids]
    if leaked:
        fail(f"practice.json must not publish sample cards: {leaked}")
    inbox = PUBLIC / "practice" / "inbox"
    if inbox.is_dir():
        for path in sorted(inbox.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items") if isinstance(payload, dict) and "items" in payload else (
                payload if isinstance(payload, list) else [payload]
            )
            wrapped = {"schema_version": 1, "items": items}
            errors = sorted(validator.iter_errors(wrapped), key=lambda e: list(e.path))
            if errors:
                first = errors[0]
                fail(f"practice/inbox/{path.name}: {first.message}")
    print(
        f"OK practice: {len(live.get('items') or [])} live, "
        f"{len(sample_ids)} sample"
    )


def check_public_ui() -> None:
    """Chinese-first pages: required labels exist, jargon stays out of visible HTML."""
    required = {
        "index.html": [
            "今天先做这 3 件",
            "精选",
            "全部",
            "今日必看",
            "市场信号",
            "重点关注",
            "不限",
            "试用工具",
            "行业动态",
            "方法模式",
            "时机窗口",
        ],
        "practice.html": ["工具用法", "创意作品", "变现", "Skill / 工作流", "硬件", "还没有可照着做的实操。"],
        "tools-radar.html": ["值得用上", "可以试", "先评估", "先别跟"],
        "subscribe.html": ["./feed.xml", "试用工具", "行业动态", "方法模式", "时机窗口"],
        "week.html": ["本周归档"],
        "agent.html": ["today3.txt", "practice.json"],
        "about.html": ["对你意味着什么", "背景与出处"],
    }
    shell = (PUBLIC / "assets" / "shell.js").read_text(encoding="utf-8")
    for label in ("今日必看", "博主实操", "本周归档", "可试用工具", "订阅更新", "给 Agent 用", "这是什么"):
        if label not in shell:
            fail(f"shell.js missing nav label {label}")
    if "比特涅槃" in shell or "AIHOT" in shell:
        fail("shell.js must not add a text wordmark besides AI / RADAR")
    cards = (PUBLIC / "assets" / "cards.js").read_text(encoding="utf-8")
    for label in ("对你意味着什么", "背景与出处", "什么情况下当这判断作废"):
        if label not in cards:
            fail(f"cards.js missing {label}")
    forbidden = ("P0-待证", "so_what", "falsifier", "比特涅槃", "AIHOT", "Tech Radar", "全部 lens")
    for name, needles in required.items():
        raw = (PUBLIC / name).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in raw:
                fail(f"{name} missing {needle}")
        visible = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", raw, flags=re.I)
        visible = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", "", visible, flags=re.I)
        for word in forbidden:
            if word in visible:
                fail(f"{name} shows jargon {word}")
        if re.search(r"\bP0\b|\bP1\b|\blens\b", visible):
            fail(f"{name} shows priority or lens jargon in visible HTML")
    print("OK public UI copy")


def main() -> None:
    try:
        from card_times import self_check as check_card_times
        from migrate_cards import check_shift_slots
    except ImportError:
        from scripts.card_times import self_check as check_card_times
        from scripts.migrate_cards import check_shift_slots
    check_card_times()
    check_shift_slots()
    check_schema()
    check_monotonic()
    check_feed()
    check_practice()
    check_public_ui()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
