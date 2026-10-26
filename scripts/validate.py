#!/usr/bin/env python3
"""CI validators: JSON Schema, archive monotonicity, feed well-formed + counts.

Also rejects obvious instruction-shaped sentences in public prose, and raw
social-post fields on public JSON. See scripts/prompt_guard.py.

Promotion traceability uses testdata/ when the private pool is absent. See docs/candidate-pool.md.

  pip install -r requirements-ci.txt
  python3 scripts/generate_derived.py && python3 scripts/validate.py

Base for the monotonic check:
  VALIDATE_BASE_SHA   (preferred; CI sets the PR base or github.event.before)
  VALIDATE_BASE_REF   (default origin/main when no SHA is set)
All-zero SHAs and a missing base are skipped with a notice. An explicit SHA
that cannot be read fails the job.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
SCHEMAS = ROOT / "schemas"
KB_EXCERPT_MAX = 80

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
# One-time public slate reset. A day may leave public/archive only when this tree
# keeps the same bytes. Later deletions still fail the monotonic check.
CUTOVER_ARCHIVE = ROOT / "retained" / "pre-auto-reset-2026-10-23" / "public" / "archive"


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
    # rumor may stay priority P0; the board renders that as 尚待核实, never as 优先看.


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


def cutover_preserved(date: str, base_raw: str) -> bool:
    path = CUTOVER_ARCHIVE / f"{date}.json"
    if not path.is_file():
        return False
    return path.read_text(encoding="utf-8") == base_raw


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
    preserved: list[str] = []
    missing_preserve: list[str] = []
    for date in sorted(removed_days):
        raw = git_show(base, f"public/archive/{date}.json")
        if raw is None:
            fail(f"missing base archive blob public/archive/{date}.json @ {base}")
        if cutover_preserved(date, raw):
            preserved.append(date)
        else:
            missing_preserve.append(date)
    if missing_preserve:
        fail(
            "archive dates removed (not monotonic): "
            + ", ".join(missing_preserve)
            + "; keep identical bytes under retained/pre-auto-reset-2026-10-23/public/archive/"
        )

    removed_keys: list[str] = []
    shrunk: list[str] = []
    for date in sorted(old_dates - set(preserved)):
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

    kept = f", {len(preserved)} days kept under the 2026-10-23 cutover" if preserved else ""
    print(
        f"OK monotonic vs {base[:12]}: +{len(new_dates - old_dates)} days, "
        f"0 days removed, 0 cards removed{kept}"
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
    check_feed_link_safety()


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
    try:
        from project_public_lanes import casual_status_title
    except ImportError:
        from scripts.project_public_lanes import casual_status_title
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
            for it in items:
                if isinstance(it, dict) and casual_status_title(str(it.get("title") or "")):
                    fail(f"practice/inbox/{path.name}: title is follower status talk, not a visitor how-to")
    live_items = [it for it in live.get("items") or [] if isinstance(it, dict)]
    note = str(live.get("note") or "")
    if "能照着做的步骤" not in note or "没有写清步骤" not in note:
        fail("practice.json note must say only finished steps are published")
    inbox_ids: list[str] = []
    if inbox.is_dir():
        for path in sorted(inbox.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items") if isinstance(payload, dict) and "items" in payload else (
                payload if isinstance(payload, list) else [payload]
            )
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    inbox_ids.append(it["id"])
    live_ids = {it.get("id") for it in live_items}
    missing = [eid for eid in inbox_ids if eid not in live_ids]
    if missing:
        fail(f"practice.json missing inbox ids (run generate_derived.py): {missing}")
    if not live_items:
        print(f"OK practice: 0 live (public slate empty), {len(sample_ids)} sample")
        return
    for it in live_items:
        steps = [s for s in (it.get("steps") or []) if isinstance(s, str) and s.strip()]
        if len(steps) < 2:
            fail(f"{it.get('id')}: live practice card needs at least 2 steps")
        if not str(it.get("caution") or "").strip():
            fail(f"{it.get('id')}: live practice card needs caution")
        if not str(it.get("takeaway") or "").strip():
            fail(f"{it.get('id')}: live practice card needs takeaway")
        if casual_status_title(str(it.get("title") or "")):
            fail(f"{it.get('id')}: practice title is follower status talk, not a visitor how-to")
    learner = ("difficulty", "prerequisites", "estimated_time", "verified")
    if not any(all(key in it and it.get(key) not in (None, "", []) for key in learner) for it in live_items):
        fail("need at least one practice card with difficulty, prerequisites, estimated_time, verified")
    print(
        f"OK practice: {len(live_items)} live, "
        f"{len(sample_ids)} sample"
    )


def check_atlas() -> None:
    """Topic atlas: schema, derived splits, practice ids mapped, topic pages exist.

    Topic status, track membership, and which card a playbook cites are content.
    They are not frozen here.
    """
    kb_path = PUBLIC / "data" / "kb.json"
    if not kb_path.is_file():
        fail("missing public/data/kb.json (run generate_derived.py)")
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((PUBLIC / "schemas" / "atlas.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(kb), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "(root)"
        fail(f"data/kb.json: schema {loc}: {first.message}")
    for name, key in (
        ("tracks.json", "tracks"),
        ("topics.json", "topics"),
        ("sources.json", "sources"),
        ("creators.json", "creators"),
    ):
        doc = json.loads((PUBLIC / "data" / name).read_text(encoding="utf-8"))
        if doc.get(key) != kb.get(key):
            fail(f"data/{name} drifted from kb.json {key}")
    topics = {item.get("slug"): item for item in kb.get("topics") or []}
    sources = kb.get("sources") or []
    by_id = {item.get("id"): item for item in sources}
    # Excerpts of third-party posts are allowed as short, attributed quotes only (docs/SECURITY.md).
    try:
        from generate_derived import safe_http_url as _safe_url
        from prompt_guard import find_instruction_override as _override
    except ImportError:
        from scripts.generate_derived import safe_http_url as _safe_url
        from scripts.prompt_guard import find_instruction_override as _override
    for item in sources:
        excerpt = str(item.get("excerpt") or "")
        if len(excerpt) > KB_EXCERPT_MAX:
            fail(f"data/kb.json {item.get('id')}: excerpt {len(excerpt)} chars > {KB_EXCERPT_MAX}; summarise, do not paste the post")
        if excerpt and (not item.get("author") or not _safe_url(str(item.get("url") or ""))):
            fail(f"data/kb.json {item.get('id')}: an excerpt needs its author and an http(s) link to the original")
        rule = _override(excerpt) or _override(str(item.get("title") or ""))
        if rule:
            fail(f"data/kb.json {item.get('id')}: excerpt/title matches {rule}")
    practice = json.loads((PUBLIC / "practice.json").read_text(encoding="utf-8"))
    for item in practice.get("items") or []:
        sid = item.get("id")
        if sid not in by_id or by_id[sid].get("origin") != "practice":
            fail(f"practice id {sid} missing from atlas sources")
    creators = kb.get("creators") or []

    def rank(creator: dict):
        primary = creator["bookmarks"] if creator.get("bookmark_metric") else creator["source_count"]
        return (-int(primary), -int(creator["source_count"]), str(creator.get("handle") or ""))

    handles = [item.get("handle") for item in creators]
    ordered = [item.get("handle") for item in sorted(creators, key=rank)]
    if handles != ordered:
        fail("atlas creators must be sorted by bookmarks when present, else source count")
    try:
        from refresh_demand import topic_save_ratio
        from score_pool import load_score_config
    except ImportError:
        from scripts.refresh_demand import topic_save_ratio
        from scripts.score_pool import load_score_config
    score_cfg = load_score_config(ROOT)
    demand_path = PUBLIC / "data" / "demand.json"
    if not demand_path.is_file():
        fail("missing public/data/demand.json (run scripts/refresh_demand.py)")
    demand = json.loads(demand_path.read_text(encoding="utf-8"))
    if demand.get("watchlist") != "unchanged":
        fail("demand.json must keep watchlist unchanged")
    if kb.get("demand_refreshed_at") != demand.get("refreshed_label"):
        fail("kb demand_refreshed_at drifted from demand.json")
    if kb.get("demand_refreshed_at_utc") != demand.get("refreshed_at"):
        fail("kb demand_refreshed_at_utc drifted from demand.json")
    rolled = demand.get("sources") or {}
    if not isinstance(rolled, dict):
        fail("demand.json sources must be an object")
    for sid, extra in rolled.items():
        if sid not in by_id:
            fail(f"demand.json source {sid} is not in the atlas")
        if not isinstance(extra, dict):
            fail(f"demand.json source {sid} must be an object")
        if by_id[sid].get("likes") != extra.get("likes") or by_id[sid].get("bookmarks") != extra.get("bookmarks"):
            fail(f"{sid} counts drifted from the demand roll")
    for item in practice.get("items") or []:
        sid = item.get("id")
        if by_id.get(sid, {}).get("verified") is not (item.get("verified") is True):
            fail(f"{sid} verified drifted from practice.json")
    for slug, topic in topics.items():
        items = [item for item in sources if item.get("topic") == slug]
        if topic.get("source_count") != len(items):
            fail(f"{slug} source_count drifted")
        samples = []
        for item in items:
            likes = item.get("likes")
            bookmarks = item.get("bookmarks")
            if isinstance(likes, int) and isinstance(bookmarks, int) and not isinstance(likes, bool) and not isinstance(bookmarks, bool):
                samples.append((bookmarks, likes))
        expect = topic_save_ratio(
            samples,
            score_cfg.bookmark_prior,
            score_cfg.like_prior,
            score_cfg.author_prior_n,
        )
        if expect is None:
            if "save_ratio" in topic:
                fail(f"{slug} save_ratio set without samples")
        elif topic.get("save_ratio") != expect:
            fail(f"{slug} save_ratio {topic.get('save_ratio')} != {expect}")
        if topic.get("demand_samples") != len(samples):
            fail(f"{slug} demand_samples drifted")
        unverified = sum(1 for item in items if item.get("origin") == "practice" and item.get("verified") is not True)
        verified_n = sum(1 for item in items if item.get("origin") == "practice" and item.get("verified") is True)
        if topic.get("unverified_practice") != unverified or topic.get("verified_practice") != verified_n:
            fail(f"{slug} verified counts drifted")
        if topic.get("demand_refreshed_at") != demand.get("refreshed_label"):
            fail(f"{slug} demand timestamp drifted")
    for slug, topic in topics.items():
        path = PUBLIC / "topics" / f"{slug}.html"
        if not path.is_file():
            fail(f"missing topics/{slug}.html")
            continue
        raw = path.read_text(encoding="utf-8")
        if f'data-slug="{slug}"' not in raw or topic.get("name") not in raw:
            fail(f"topics/{slug}.html missing slug or title")
        if 'src="../assets/atlas.js"' not in raw or 'src="../assets/shell.js"' not in raw:
            fail(f"topics/{slug}.html must load shell.js and atlas.js")
    print(f"OK atlas: {len(topics)} topics, {len(sources)} sources")


def check_public_ui() -> None:
    """Chinese-first pages: required labels exist, jargon stays out of visible HTML."""
    required = {
        "index.html": [
            "今天，什么值得关注？",
            "看信息精选",
            "./today.html",
            "./briefs.html",
            "./tools-radar.html",
            "./atlas.html",
            "./observe.html",
            "信息精选",
            "工具与产品",
            "信息简讯",
            "把发现变成能力",
            "工具决策",
            "实战手册",
            "专题观察",
            "值得采用",
            "给迷途者的代码，给觉醒者的诗。",
            "未经证实的传闻与第三方帖子",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
        ],
        "blog/index.html": [
            "随笔",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
        ],
        "atlas.html": [
            "实战手册",
            "实战图谱",
            "信息精选",
            "./today.html",
            "做法条目",
            "博主库",
            "待采集",
            "造物",
            "内容创作",
            "开发提效",
            "知识管理",
            "商业化",
            "收录标准",
            "编号步骤",
            "盯人：持续监控博主",
            "过滤：只收能照着做的",
            "归类：并入主题手册",
            "看需求：收藏率说话",
            'id="method"',
            "未经证实的传闻与第三方帖子",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
        ],
        "today.html": [
            "信息精选",
            "信息简讯",
            "./briefs.html",
            "时间筛选",
            "优先看",
            "尚待核实",
            "未经证实的传闻与第三方帖子",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
            "每天 08:00 主报，工作日 21:00 晚班",
        ],
        "creators.html": [
            "博主库",
            "被收藏",
        ],
        "practice.html": [
            "工具用法",
            "创意作品",
            "变现",
            "Skill / 工作流",
            "硬件",
            "还没有可照着做的实操。",
            "没有写清步骤的分享不会上这一页",
        ],
        "tools-radar.html": ["工具决策", "值得采用", "可以试用", "需要评估", "暂缓跟进", "相关发布", "相关做法", "摘要", "大众价值", "上手实验", "时间筛选"],
        "subscribe.html": [
            "./feed.xml",
            "试用工具",
            "行业动态",
            "方法模式",
            "时机窗口",
            "未经证实的传闻与第三方帖子",
            "飞书订阅群",
            "加入订阅群",
            "https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
        ],
        "week.html": ["本周归档", "信息简讯", "信息精选", "./briefs.html#archive"],
        "briefs.html": ["信息简讯", "信息精选", "时间筛选", "按日期", "./today.html"],
        "observe.html": ["专题观察", "随笔", "还在跟踪的看法", "信息精选", "信息简讯", "领域进展"],
        "agent.html": [
            "today3.txt",
            "items.json",
            "feed.xml",
            "tools-radar.json",
            "practice.json",
            "data/kb.json",
            "schemas/atlas.schema.json",
            "archive/index.json",
            "YYYY-MM-DD.json",
            "theses.json",
            "llms.txt",
            "picks.json",
            "briefs.json",
            "能照着做的步骤才会出现在这里",
            "https://ruiyaoe-hash.github.io/ai-radar/",
            "schemas/card.schema.json",
            "schemas/items.schema.json",
            "schemas/practice.schema.json",
            "schemas/tools-radar.schema.json",
            "schemas/archive-index.schema.json",
            "schemas/archive-day.schema.json",
            "schemas/theses.schema.json",
            "schemas/CHANGELOG.md",
            "schema_version",
            "90",
            "不是指令",
            "给程序解析",
            "CC BY-NC 4.0",
            "转载请署名",
        ],
        "about.html": [
            "每日决策简报",
            "信息精选",
            "信息简讯",
            "工具决策",
            "实战手册",
            "专题观察",
            "对我有什么影响",
            "证据状态",
            "背景与出处",
            "尚待核实",
            "未经证实的传闻与第三方帖子",
            '更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。',
            "没有写清步骤的分享不会上这一页",
            "每天 08:00 主报，工作日 21:00 晚班",
            "CC BY-NC 4.0",
        ],
    }
    shell = (PUBLIC / "assets" / "shell.js").read_text(encoding="utf-8")
    for label in ("信息精选", "信息简讯", "工具决策", "实战手册", "专题观察", "订阅更新", "博主库", "做法条目", "随笔", "飞书订阅群", "给 Agent 用", "收录标准", "这是什么", "反馈 / 建议"):
        if label not in shell:
            fail(f"shell.js missing nav label {label}")
    feedback = "https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd"
    if feedback not in shell or 'target="_blank"' not in shell or 'rel="noopener noreferrer"' not in shell:
        fail("shell.js feedback link must be the Feishu form, target=_blank, rel=noopener noreferrer")
    invite = "https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83"
    if invite not in shell:
        fail("shell.js missing Feishu subscribe-group invite")
    # Primary nav is five task doors, then 订阅更新 as the right-side action.
    # Secondary links live under 更多. Old 信号 / 造物 / 共鸣 groups are not the nav.
    primary = ["信息精选", "信息简讯", "工具决策", "实战手册", "专题观察"]
    cursor = 0
    for label in primary:
        pos = shell.find(label, cursor)
        if pos < 0:
            fail(f"shell.js primary nav missing {label}")
        cursor = pos + len(label)
    calls = [
        'href: "today.html"',
        'href: "briefs.html"',
        'href: "tools-radar.html"',
        'href: "atlas.html"',
        'href: "observe.html"',
    ]
    call_at = [shell.find(call) for call in calls]
    if any(pos < 0 for pos in call_at) or call_at != sorted(call_at):
        fail("shell.js primary links must be today, briefs, tools, atlas, observe in that order")
    more_at = shell.find('id: "more"')
    subscribe_at = shell.find("订阅更新")
    if more_at < 0 or subscribe_at < more_at or more_at < call_at[-1]:
        fail("shell.js must keep 更多 after the five doors and 订阅更新 as the action")
    more_labels = ["博主库", "做法条目", "随笔", "飞书订阅群", "给 Agent 用", "收录标准", "这是什么", "反馈 / 建议"]
    more_calls = [
        'item("creators.html"',
        'item("practice.html"',
        'item("blog/"',
        "item(FEISHU_GROUP",
        'item("agent.html"',
        'item("atlas.html#method"',
        'item("about.html"',
        "item(FEEDBACK_FORM",
    ]
    segment = shell[more_at:subscribe_at]
    pos = [segment.find(label) for label in more_labels]
    if any(p < 0 for p in pos) or pos != sorted(pos) or any(call not in segment for call in more_calls):
        fail("shell.js 更多 must list 博主库 / 做法条目 / 随笔 / 飞书订阅群 / 给 Agent 用 / 收录标准 / 这是什么 / 反馈 / 建议")
    for rel in ("assets/shell.js", "subscribe.html"):
        mirror = ROOT / rel
        if not mirror.exists():
            continue
        mirrored = mirror.read_text(encoding="utf-8")
        if invite not in mirrored or "飞书订阅群" not in mirrored:
            fail(f"{rel} root mirror missing Feishu subscribe-group invite")
    if "AIHOT" in shell:
        fail("shell.js must not add another wordmark besides AI Radar")
    cards = (PUBLIC / "assets" / "cards.js").read_text(encoding="utf-8")
    for label in ("发生了什么", "为什么值得看", "对我有什么影响", "建议行动", "证据状态", "背景与出处", "什么情况下当这判断作废"):
        if label not in cards:
            fail(f"cards.js missing {label}")
    if "so_what.confidence" in cards or ".confidence" in cards:
        fail("cards.js must not render confidence or a raw score")
    atlas_js = (PUBLIC / "assets" / "atlas.js").read_text(encoding="utf-8")
    if "先验" in atlas_js or "toFixed(2)" in atlas_js or "save_ratio" in atlas_js:
        fail("atlas.js must not print ratio scores or a prior formula")
    forbidden = ("P0-待证", "so_what", "falsifier", "AIHOT", "Tech Radar", "全部 lens")
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
        if "先验" in visible or re.search(r"需求信号\s*\d", visible):
            fail(f"{name} shows a ratio score or a prior formula")
        if "13:30" in visible or "从监控信源里捞" in visible:
            fail(f"{name} still shows a removed schedule slot or an auto-scrape claim")
    # Visitor help pages name what you can open. Internal systems stay in docs/SECURITY.md.
    runbook = (
        "私有候选池",
        "webhook 密钥",
        "访问令牌",
        "门槛日志",
        "不可信文本",
        "不公开",
        "仓库校验",
        "Cloudflare Web Analytics",
    )
    for name in ("agent.html", "llms.txt"):
        text = (PUBLIC / name).read_text(encoding="utf-8")
        for phrase in runbook:
            if phrase in text:
                fail(f"{name} reads like an internal runbook: {phrase}")
    shell_visible = shell
    if "13:30" in shell_visible:
        fail("shell.js still shows 13:30")
    print("OK public UI copy")


def check_blog() -> None:
    """content/posts and public/blog agree; the renderer escapes and filters links."""
    try:
        import build_blog
    except ImportError:
        from scripts import build_blog
    build_blog.self_check()
    posts = build_blog.load_posts()
    index = PUBLIC / "blog" / "posts.json"
    if not index.is_file():
        fail("missing public/blog/posts.json (run scripts/generate_derived.py)")
    doc = json.loads(index.read_text(encoding="utf-8"))
    listed = [p.get("slug") for p in doc.get("posts", [])]
    if listed != [p["slug"] for p in posts]:
        fail("public/blog/posts.json is stale: run scripts/generate_derived.py")
    for i, post in enumerate(posts):
        page = PUBLIC / "blog" / f"{post['slug']}.html"
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        if not page.is_file() or page.read_text(encoding="utf-8") != build_blog.render_post(post, newer, older):
            fail(f"public/blog/{post['slug']}.html is stale: run scripts/generate_derived.py")
        url = doc["posts"][i].get("url", "")
        if not url.startswith(SITE_BASE + "blog/"):
            fail(f"blog post url must live under the site: {url!r}")
    print(f"OK blog: {len(posts)} posts rendered from content/posts")


def check_feed_link_safety() -> None:
    paths = [PUBLIC / "feed.xml", *sorted((PUBLIC / "feeds").glob("*.xml"))]
    for path in paths:
        for el in parse_feed(path):
            link = (el.findtext("link") or "").strip()
            if re.search(r"javascript\s*:", link, re.I):
                fail(f"{path.name}: javascript: in item link {link!r}")
            parts = urllib.parse.urlsplit(link)
            if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
                fail(f"{path.name}: item link is not http(s): {link!r}")
    print("OK feed links: http(s) only, no javascript:")


def check_rss_escape() -> None:
    """A hostile card must not become a raw tag or a javascript: item link."""
    try:
        from generate_derived import SITE, build_rss
    except ImportError:
        from scripts.generate_derived import SITE, build_rss

    evil = {
        "id": "evt-20261013-xss-probe",
        "title": "</title><script>alert(1)</script>",
        "url": "javascript:alert(1)",
        "try_url": "data:text/html,<script>alert(2)</script>",
        "date": "2026-10-13",
        "lens": "工具",
        "tag": "<script>tag</script>",
        "priority": "P0",
        "status": "rumor",
        "objective": ["]]> <img src=x onerror=alert(1)>", "<script>alert(3)</script>"],
        "so_what": {
            "impact": "<script>alert(4)</script>",
            "action": "javascript:alert(5)",
            "window": "now",
            "confidence": "<b>x</b>",
            "falsifier": "]]></description><script>alert(6)</script>",
        },
        "sources": [
            {"handle": "<script>h</script>", "role": "primary", "url": "javascript:alert(7)"}
        ],
        "correction": {"note": "<script>c</script>"},
    }
    xml = build_rss([evil], "t <script>", "d <script>alert(1)</script>", SITE + "feed.xml")
    if re.search(r"<\s*script", xml, re.I):
        fail("RSS emitter wrote a raw script tag")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        fail(f"malicious card broke RSS: {exc}")
    link = root.findtext("./channel/item/link") or ""
    if re.search(r"javascript\s*:", link, re.I) or not link.startswith("https://"):
        fail(f"unsafe card url was not replaced with an https permalink: {link!r}")
    desc = root.findtext("./channel/item/description") or ""
    if "<script" in desc.lower() or "]]>" in desc:
        fail("description decoded to raw markup or a CDATA terminator")
    if "&lt;script&gt;" not in desc:
        fail("card text was not HTML-escaped inside the RSS description")
    print("OK rss escaping: card text is escaped, bad urls leave the item link")


INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", re.I | re.S)
CSP_META_RE = re.compile(
    r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"\s*/?>',
    re.I,
)


def csp_hash(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


# Cloudflare Web Analytics beacon. script host serves beacon.min.js; connect host
# receives the RUM POST at https://cloudflareinsights.com/cdn-cgi/rum.
CF_SCRIPT_ORIGIN = "https://static.cloudflareinsights.com"
CF_CONNECT_ORIGIN = "https://cloudflareinsights.com"
CF_BEACON_SNIPPET = (
    "<!-- Cloudflare Web Analytics -->"
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"964a2081359a4ef8aa36617df12bae1f\"}'></script>"
    "<!-- End Cloudflare Web Analytics -->"
)


def expected_csp(hashes: list[str]) -> str:
    script = " ".join(["'self'", *hashes, CF_SCRIPT_ORIGIN])
    return (
        "default-src 'self'; "
        f"script-src {script}; "
        "script-src-attr 'none'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "font-src 'self'; "
        f"connect-src 'self' {CF_CONNECT_ORIGIN}; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-src 'none'"
    )


def iter_public_html() -> list[Path]:
    pages = list(PUBLIC.glob("*.html"))
    for sub in ("topics", "blog"):
        folder = PUBLIC / sub
        if folder.is_dir():
            pages.extend(folder.glob("*.html"))
    return sorted(pages)


def loads_shell(raw: str) -> bool:
    return 'src="./assets/shell.js"' in raw or 'src="../assets/shell.js"' in raw


def check_csp() -> None:
    pages = iter_public_html()
    if not pages:
        fail("no public HTML pages")
    for path in pages:
        raw = path.read_text(encoding="utf-8")
        found = CSP_META_RE.findall(raw)
        if len(found) != 1:
            fail(f"{path.name}: expected one Content-Security-Policy meta, found {len(found)}")
        if raw.find("Content-Security-Policy") > raw.lower().find("<script"):
            fail(f"{path.name}: CSP meta must come before the first script")
        hashes = [csp_hash(body) for body in INLINE_SCRIPT_RE.findall(raw)]
        policy = found[0]
        expect = expected_csp(hashes)
        if policy != expect:
            fail(f"{path.name}: CSP mismatch\n  got:  {policy}\n  want: {expect}")
        scrubbed = policy.replace(CF_SCRIPT_ORIGIN, "").replace(CF_CONNECT_ORIGIN, "").lower()
        for banned in ("unsafe-inline", "unsafe-eval", "http://", "https://", "*", "data:", "blob:"):
            if banned in scrubbed:
                fail(f"{path.name}: CSP allows {banned}")
    print(f"OK csp: {len(pages)} html pages, script-src self + inline hashes + cloudflare beacon")


def check_beacon() -> None:
    shell = (PUBLIC / "assets" / "shell.js").read_text(encoding="utf-8")
    if CF_BEACON_SNIPPET not in shell:
        fail("shell.js must include the Cloudflare Web Analytics snippet with the exact token")
    if "installCfBeacon" not in shell or "DOMContentLoaded" not in shell:
        fail("shell.js must install the beacon on DOMContentLoaded, before </body>")
    pages = iter_public_html()
    for path in pages:
        raw = path.read_text(encoding="utf-8")
        if not loads_shell(raw):
            fail(f"{path.relative_to(PUBLIC)}: must load shell.js so the analytics beacon is injected")
    print(f"OK beacon: exact snippet via shell.js on {len(pages)} html pages")


def check_safe_href() -> None:
    helper = (PUBLIC / "assets" / "safe-href.js").read_text(encoding="utf-8")
    cards = (PUBLIC / "assets" / "cards.js").read_text(encoding="utf-8")
    shell = (PUBLIC / "assets" / "shell.js").read_text(encoding="utf-8")
    if "function safeHref" not in helper:
        fail("safe-href.js missing safeHref")
    if "function externalAnchor" not in cards or "safeHref" not in cards:
        fail("cards.js must build anchors with safeHref")
    if re.search(r"esc\((?:s\.url|it\.url|it\.try_url)\)", cards):
        fail("cards.js still puts a raw card url through esc() into markup")
    if "safeHref(" not in shell:
        fail("shell.js must filter nav hrefs with safeHref")
    atlas = PUBLIC / "assets" / "atlas.js"
    if not atlas.is_file() or "safeHref(" not in atlas.read_text(encoding="utf-8"):
        fail("atlas.js must filter links with safeHref")
    linked = {"tools-radar.html": "assets/tools.js"}
    for name in ("practice.html", "tools-radar.html", "subscribe.html"):
        raw = (PUBLIC / name).read_text(encoding="utf-8")
        extra = ""
        script = linked.get(name)
        if script:
            if script not in raw:
                fail(f"{name} must load {script}")
            extra = (PUBLIC / script).read_text(encoding="utf-8")
        if "safeHref(" not in raw and "safeHref(" not in extra:
            fail(f"{name} builds anchors without safeHref")
        if re.search(r"esc\(it\.(?:url|try_url)\)", raw):
            fail(f"{name} still puts a raw card url through esc() into href")
    script = ROOT / "scripts" / "test_safe_href.js"
    proc = subprocess.run(
        ["node", str(script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        fail(f"safeHref tests failed\n{proc.stdout}\n{proc.stderr}")
    print(proc.stdout.strip())


def _string_list(value, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            fail(f"{label} entries must be non-empty strings")
        out.append(item.strip())
    folded = [item.casefold() for item in out]
    if len(folded) != len(set(folded)):
        fail(f"{label} has duplicate entries")
    return out


def check_practice_handles() -> None:
    """Watch lists are string lists. Membership is config, not a frozen roster."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    practice = _string_list(cfg.get("practice_handles"), "practice_handles")
    a_tier = _string_list(cfg.get("a_tier"), "a_tier")
    overlap = sorted({item.casefold() for item in practice} & {item.casefold() for item in a_tier})
    if overlap:
        fail(f"practice_handles still listed in a_tier: {overlap}")
    digests = cfg.get("digests")
    if digests is not None:
        if not isinstance(digests, list):
            fail("digests must be a list")
        for slot in digests:
            if not isinstance(slot, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", slot):
                fail(f"digests entries must be HH:MM, got {slot!r}")
    print("OK practice_handles: string lists, disjoint from a_tier")


def check_private_surface() -> None:
    """Published files must not carry the private digest or live owner actions."""
    actions_path = PUBLIC / "owner-actions.json"
    if actions_path.is_file():
        data = json.loads(actions_path.read_text(encoding="utf-8"))
        if data.get("example_only") is not True:
            fail("public/owner-actions.json must set example_only true")
        if data.get("actions") not in ([], None):
            fail("public/owner-actions.json must not publish action rows; use owner-actions.local.json")
    digest_path = ROOT / "DIGEST_LATEST.md"
    if not digest_path.is_file():
        fail("DIGEST_LATEST.md missing; keep the public skeleton")
    digest = digest_path.read_text(encoding="utf-8")
    if "不是私人实时主报" not in digest:
        fail("DIGEST_LATEST.md must stay a public skeleton, not a private digest")
    if "主人，" in digest:
        fail("DIGEST_LATEST.md must not address a private digest")
    print("OK private surface: digest skeleton, empty public owner-actions")


def check_topic_suggestions() -> None:
    """Public suggestions cover practice cards and never look published."""
    path = PUBLIC / "data" / "topic-suggestions.json"
    if not path.is_file():
        fail("missing public/data/topic-suggestions.json (run scripts/suggest_atlas_topics.py)")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_text(encoding="utf-8")
    for banned in ("status_in_pool", "snippet", "\"steps\""):
        if banned in raw:
            fail(f"topic-suggestions.json contains {banned}")
    practice = json.loads((PUBLIC / "practice.json").read_text(encoding="utf-8"))
    atlas = json.loads((PUBLIC / "data" / "atlas.source.json").read_text(encoding="utf-8"))
    slugs = {item.get("slug") for item in atlas.get("topics") or []}
    expected = {item.get("id") for item in practice.get("items") or [] if item.get("id")}
    seen: list[str] = []
    for item in data.get("items") or []:
        item_id = str(item.get("id") or "")
        seen.append(item_id)
        if not item_id.startswith("prac-"):
            fail(f"public topic suggestion {item_id} is outside the practice lane")
        if item.get("verified") is not True and item.get("apply") == "held":
            fail(f"{item_id} is unverified but marked held")
        if item.get("verified") is True and item.get("topic") and item.get("apply") != "held":
            fail(f"{item_id} verified suggestion must stay held until a person confirms")
        if item.get("apply") == "no_topic" and item.get("topic") is not None:
            fail(f"{item_id} no_topic still names a topic")
        if item.get("topic") is not None and item.get("topic") not in slugs:
            fail(f"{item_id} topic {item.get('topic')} is not in the atlas")
        for key in ("steps", "snippet", "notes", "status_in_pool"):
            if key in item:
                fail(f"{item_id} suggestion carries {key}")
    if set(seen) != expected or len(seen) != len(set(seen)):
        fail("topic suggestions must list each public practice card once")
    print(f"OK topic suggestions: {len(seen)} practice cards, none applied")


def check_derive_ignores_pool() -> None:
    src = (ROOT / "scripts" / "generate_derived.py").read_text(encoding="utf-8")
    for banned in ("ai-radar-pool", "status_in_pool", "ingest_x", "candidates/"):
        if banned in src:
            fail(f"generate_derived.py must not reference {banned}")
    print("OK derive: archive, practice inbox, and public demand overlay; pool is not an input")


PUBLISHED_SCHEMA_DOCS = {
    "items.json": "items.schema.json",
    "practice.json": "practice.schema.json",
    "data/kb.json": "atlas.schema.json",
    "tools-radar.json": "tools-radar.schema.json",
    "archive/index.json": "archive-index.schema.json",
    "theses.json": "theses.schema.json",
    "briefs.json": "briefs.schema.json",
    "data/demand.json": "demand.schema.json",
    "data/topic-suggestions.json": "topic-suggestions.schema.json",
}
SITE_BASE = "https://ruiyaoe-hash.github.io/ai-radar/"
PRIVATE_SURFACE = (
    "candidate.schema",
    "ai-radar-pool",
    "status_in_pool",
    "AI_RADAR_POOL",
    "FEISHU_BOT",
)


def check_published_schemas() -> None:
    """Public Agent surface: published schemas match the feeds, and the pool schema stays off Pages."""
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")

    pub_dir = PUBLIC / "schemas"
    if not pub_dir.is_dir():
        fail("public/schemas missing")
    for path in pub_dir.iterdir():
        if path.is_file() and "candidate" in path.name:
            fail(f"public/schemas must not publish {path.name}")
    for name in (
        "card.schema.json",
        "practice.schema.json",
        "archive-day.schema.json",
        "atlas.schema.json",
        "briefs.schema.json",
        "demand.schema.json",
        "topic-suggestions.schema.json",
    ):
        src = SCHEMAS / name
        dst = pub_dir / name
        if not dst.is_file():
            fail(f"public/schemas/{name} missing")
        if src.read_bytes() != dst.read_bytes():
            fail(f"public/schemas/{name} drifted from schemas/{name}")

    by_name: dict[str, dict] = {}
    resources = []
    for path in sorted(pub_dir.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        by_name[path.name] = schema
        res = Resource(contents=schema, specification=DRAFT202012)
        resources.append((schema.get("$id") or path.name, res))
        resources.append((path.name, res))
        resources.append((SITE_BASE + "schemas/" + path.name, res))
    registry = Registry().with_resources(resources)

    def reject(rel: str, schema_name: str, data) -> None:
        validator = Draft202012Validator(by_name[schema_name], registry=registry)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if not errors:
            return
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "(root)"
        fail(f"{rel}: published schema {loc}: {first.message}")

    for rel, schema_name in PUBLISHED_SCHEMA_DOCS.items():
        data = json.loads((PUBLIC / rel).read_text(encoding="utf-8"))
        reject(rel, schema_name, data)
    day_name = "archive-day.schema.json"
    n_days = 0
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        reject(f"archive/{path.name}", day_name, json.loads(path.read_text(encoding="utf-8")))
        n_days += 1
    if n_days == 0:
        print("note: public/archive has no day files; historical days live under retained/pre-auto-reset-2026-10-23/")

    changelog = (pub_dir / "CHANGELOG.md").read_text(encoding="utf-8")
    for needle in ("schema_version", "90"):
        if needle not in changelog:
            fail(f"schemas/CHANGELOG.md missing {needle}")
    llms = (PUBLIC / "llms.txt").read_text(encoding="utf-8")
    if "<html" in llms.lower():
        fail("llms.txt must be plain text")
    for rel in (
        "agent.html",
        "today3.txt",
        "items.json",
        "feed.xml",
        "feeds/lens-tools.xml",
        "feeds/lens-tracks.xml",
        "feeds/lens-models.xml",
        "feeds/lens-timing.xml",
        "tools-radar.json",
        "practice.json",
        "data/kb.json",
        "data/demand.json",
        "data/topic-suggestions.json",
        "data/tracks.json",
        "data/topics.json",
        "data/sources.json",
        "data/creators.json",
        "schemas/atlas.schema.json",
        "schemas/demand.schema.json",
        "schemas/topic-suggestions.schema.json",
        "archive/index.json",
        "theses.json",
        "schemas/CHANGELOG.md",
        "schemas/card.schema.json",
        "schemas/items.schema.json",
        "schemas/practice.schema.json",
        "schemas/tools-radar.schema.json",
        "schemas/archive-index.schema.json",
        "schemas/archive-day.schema.json",
        "schemas/theses.schema.json",
    ):
        if SITE_BASE + rel not in llms:
            fail(f"llms.txt missing {SITE_BASE}{rel}")
    for label, text in (
        ("agent.html", (PUBLIC / "agent.html").read_text(encoding="utf-8")),
        ("llms.txt", llms),
        ("schemas/CHANGELOG.md", changelog),
    ):
        for banned in PRIVATE_SURFACE:
            if banned in text:
                fail(f"{label} exposes private surface {banned!r}")
    print(f"OK published schemas: {len(PUBLISHED_SCHEMA_DOCS)} docs, {n_days} archive days; pool schema stays off Pages")


def check_prompt_injection() -> None:
    """Fail CI when public prose looks like an imperative jailbreak.

    Fixtures cover true positives and near-miss benign sentences (system-prompt
    news, "you are now able"). Live archive, items, practice, theses, tools,
    today3, and memos are scanned. Raw post keys are rejected on public JSON.
    """
    try:
        from human_layer import _self_check as human_self_check
        from prompt_guard import (
            check_fixtures,
            find_instruction_override,
            iter_public_prose,
            iter_public_raw_keys,
        )
    except ImportError:
        from scripts.human_layer import _self_check as human_self_check
        from scripts.prompt_guard import (
            check_fixtures,
            find_instruction_override,
            iter_public_prose,
            iter_public_raw_keys,
        )

    if human_self_check() != 0:
        fail("human_layer self-check failed")
    derived = (ROOT / "scripts" / "generate_derived.py").read_text(encoding="utf-8")
    if "strip_raw_post_fields" not in derived:
        fail("generate_derived.py must strip raw post fields before writing public JSON")
    migrated = (ROOT / "scripts" / "migrate_cards.py").read_text(encoding="utf-8")
    if "strip_raw_post_fields" not in migrated:
        fail("migrate_cards.py must strip raw post fields when writing a card")

    errors = check_fixtures(ROOT)
    if errors:
        fail("prompt-injection fixtures:\n  " + "\n  ".join(errors))

    hits = []
    for where, field, text in iter_public_prose(PUBLIC):
        rule = find_instruction_override(text)
        if rule:
            hits.append(f"{where} {field} matches {rule}")
    raw = list(iter_public_raw_keys(PUBLIC))
    if hits or raw:
        shown = (hits + raw)[:20]
        extra = len(hits) + len(raw) - len(shown)
        tail = f"\n  … {extra} more" if extra > 0 else ""
        fail("public prompt-injection check:\n  " + "\n  ".join(shown) + tail)
    print("OK prompt injection: fixtures, edited public prose, no raw post fields")


def check_public_copy() -> None:
    """Visitor cards are finished Chinese. Workflow talk never reaches public files."""
    try:
        from editorial_zh import SCAFFOLD, visitor_ready
    except ImportError:
        from scripts.editorial_zh import SCAFFOLD, visitor_ready
    scaffold_hits: list[str] = []
    for path in PUBLIC.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".js", ".json", ".txt", ".md"}:
            continue
        if "schemas" in path.relative_to(PUBLIC).parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for phrase in SCAFFOLD:
            if phrase.lower() in lowered:
                scaffold_hits.append(f"{path.relative_to(PUBLIC)} contains {phrase}")
    if scaffold_hits:
        fail("public scaffolding:\n  " + "\n  ".join(scaffold_hits[:20]))

    prose_hits: list[str] = []

    def take(where: str, key: str, value: object) -> None:
        if isinstance(value, str) and value.strip() and not visitor_ready(value):
            prose_hits.append(f"{where} {key}")

    def card(where: str, item: dict) -> None:
        for key in ("title", "summary", "why", "affect", "audience_value", "first_step", "takeaway"):
            if key in item:
                take(where, key, item.get(key))
        so = item.get("so_what") if isinstance(item.get("so_what"), dict) else {}
        for key in ("impact", "falsifier", "window"):
            if key in so:
                take(where, key, so.get(key))
        for key in ("objective", "bullets", "judgment", "steps"):
            for index, line in enumerate(item.get(key) or []):
                take(where, f"{key}[{index}]", line)

    targets = [
        PUBLIC / "briefs.json",
        PUBLIC / "items.json",
        PUBLIC / "picks.json",
        PUBLIC / "tools-radar.json",
        PUBLIC / "practice.json",
        PUBLIC / "practice.sample.json",
        PUBLIC / "data" / "watch.json",
        PUBLIC / "theses.json",
    ]
    targets.extend(sorted((PUBLIC / "archive").glob("????-??-??.json")))
    for path in targets:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows: list[dict] = []
        if isinstance(data, dict):
            rows.extend(item for item in data.get("items") or [] if isinstance(item, dict))
            rows.extend(item for item in data.get("theses") or [] if isinstance(item, dict))
            rows.extend(item for item in data.get("stream") or [] if isinstance(item, dict))
            for day in data.get("days") or []:
                if isinstance(day, dict):
                    rows.extend(item for item in day.get("items") or [] if isinstance(item, dict))
            rings = data.get("rings") if isinstance(data.get("rings"), dict) else {}
            for group in rings.values():
                if isinstance(group, list):
                    rows.extend(item for item in group if isinstance(item, dict))
        rel = path.relative_to(PUBLIC)
        for item in rows:
            card(f"{rel}:{item.get('id') or item.get('title')}", item)
    if prose_hits:
        fail("public copy is not visitor-ready:\n  " + "\n  ".join(prose_hits[:20]))
    print("OK public copy: finished Chinese, no scaffolding")


def check_briefs() -> None:
    """L2 briefs stay factual: schema, safe URLs, no raw post keys, no instruction text."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((SCHEMAS / "briefs.schema.json").read_text(encoding="utf-8"))
    data = json.loads((PUBLIC / "briefs.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(part) for part in first.path) or "(root)"
        fail(f"briefs.json schema {loc}: {first.message}")
    try:
        from generate_derived import safe_http_url
        from prompt_guard import find_instruction_override, raw_post_key_paths
    except ImportError:
        from scripts.generate_derived import safe_http_url
        from scripts.prompt_guard import find_instruction_override, raw_post_key_paths
    raw = raw_post_key_paths(data)
    if raw:
        fail(f"briefs.json has raw post keys: {raw}")
    for item in data.get("items") or []:
        for field in ("title", "summary", "source"):
            rule = find_instruction_override(str(item.get(field) or ""))
            if rule:
                fail(f"briefs.json {item.get('id')} {field} matches {rule}")
            if re.search(r"</?[A-Za-z][^<>]*>|&(lt|gt|amp|quot|#\d+);", str(item.get(field) or "")):
                fail(f"briefs.json {item.get('id')} {field} carries feed HTML")
        if not safe_http_url(item.get("url") or ""):
            fail(f"briefs.json {item.get('id')} url is not http(s)")
        for banned in ("so_what", "priority", "status", "snippet", "score", "force_p0", "components", "value"):
            if banned in item:
                fail(f"briefs.json {item.get('id')} must not carry {banned}")
        copy = item.get("card_copy")
        if isinstance(copy, dict) and copy.get("high_priority_review"):
            fail(f"briefs.json {item.get('id')} must not carry a high-priority review flag")
    page = (PUBLIC / "briefs.html").read_text(encoding="utf-8")
    if "本页当前为示例数据" in page:
        fail("briefs.html still describes the page as sample data")
    if "信息简讯" not in page:
        fail("briefs.html should name the visitor door")
    script = (PUBLIC / "assets" / "briefs.js").read_text(encoding="utf-8")
    if "archive/" in script:
        fail("briefs.js must not load the archive; picks and briefs stay separate")
    if "blocked_urls" not in script:
        fail("briefs.js must drop items that already belong to 信息精选")
    try:
        from editorial_zh import visitor_ready
    except ImportError:
        from scripts.editorial_zh import visitor_ready
    picks_path = PUBLIC / "picks.json"
    if not picks_path.is_file():
        fail("missing public/picks.json (run generate_derived.py)")
    picks = json.loads(picks_path.read_text(encoding="utf-8"))
    blocked_urls = {str(url).rstrip("/").lower() for url in picks.get("blocked_urls") or []}
    blocked_ids = {str(item_id) for item_id in picks.get("blocked_ids") or []}
    for item in data.get("items") or []:
        for field in ("title", "summary", "why", "affect"):
            text = str(item.get(field) or "")
            if not visitor_ready(text):
                fail(f"briefs.json {item.get('id')} {field} is not finished Chinese visitor copy")
        url = str(item.get("url") or "").rstrip("/").lower()
        if url and url in blocked_urls:
            fail(f"briefs.json {item.get('id')} repeats a pick url")
        if item.get("id") in blocked_ids or item.get("candidate_id") in blocked_ids:
            fail(f"briefs.json {item.get('id')} repeats a pick id")
    derive = (ROOT / "scripts" / "derive_briefs.py").read_text(encoding="utf-8")
    for needle in ("safe_http_url", "find_instruction_override", "strip_raw_post_fields", "practice"):
        if needle not in derive:
            fail(f"derive_briefs.py must mention {needle}")
    if ' / "practice"' not in derive and "public/practice" not in derive:
        fail("derive_briefs.py must refuse the practice inbox path")
    print(f"OK briefs: {len(data.get('items') or [])} items, schema, safe url, no raw post")


def check_pool_workflows() -> None:
    """RSS and X ingest rebase before push. X live fetch stays behind a secret name."""
    rss = (ROOT / ".github" / "workflows" / "ingest-rss-pool.yml").read_text(encoding="utf-8")
    watch = (ROOT / ".github" / "workflows" / "ingest-x-pool.yml").read_text(encoding="utf-8")
    for label, text in (("rss", rss), ("x", watch)):
        if "workflow_dispatch" not in text or "pool_git_push.sh" not in text:
            fail(f"{label} workflow must keep workflow_dispatch and pool_git_push.sh")
        if "score_pool.py" not in text or "derive_briefs.py" not in text:
            fail(f"{label} workflow must score and derive briefs")
        if "project_public_lanes.py" not in text or "generate_derived.py" not in text:
            fail(f"{label} workflow must project practice and watch, then derive public pages")
    if "X_BEARER_TOKEN" not in watch or "shift_ingest_x_to_pool.py" not in watch:
        fail("X workflow must name X_BEARER_TOKEN and keep the hand-feed ingest")
    if "AI_RADAR_POOL_TOKEN" not in rss:
        fail("RSS workflow must keep AI_RADAR_POOL_TOKEN")
    for label, text in (("rss", rss), ("x", watch)):
        for needle in (
            "group: pool-writer",
            "cancel-in-progress: false",
            "public_briefs_push.sh",
            "pull-requests: write",
        ):
            if needle not in text:
                fail(f"{label} workflow must carry {needle}")
        if "gh workflow run deploy-pages.yml" in text:
            fail(f"{label} workflow must not dispatch deploy-pages before the briefs PR merges")
        if "persist-credentials: true" in text:
            fail(f"{label} workflow must not persist a token into .git/config")
    if watch.count("X_BEARER_TOKEN: ${{ secrets.X_BEARER_TOKEN }}") != 1:
        fail("X_BEARER_TOKEN must be in exactly one step env (the fetch)")
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        copy = ROOT / "docs" / "workflows" / path.name
        if not copy.is_file() or copy.read_text(encoding="utf-8") != text:
            fail(f"docs/workflows/{path.name} drifted from .github/workflows")
        for match in re.finditer(r"uses:\s*([\w./-]+)@(\S+)", text):
            if not re.fullmatch(r"[0-9a-f]{40}", match.group(2)):
                fail(f"{path.name}: {match.group(1)} must be pinned to a commit SHA, not {match.group(2)}")
        for block in re.finditer(r"run: \|\n((?:[ ]{10,}.*\n|\s*\n)+)|run: (.+)", text):
            body = block.group(1) or block.group(2) or ""
            if "${{" in body:
                fail(f"{path.name}: pass expressions through env:, not inline in run:")
    print(f"OK pool workflows: dispatch, rebase push, score, briefs; {len(workflows)} workflows pinned and mirrored")


def check_public_excludes_pool() -> None:
    for path in PUBLIC.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PUBLIC)
        if path.suffix == ".jsonl" or "candidates" in rel.parts:
            fail(f"public/ must not contain pool output: {rel}")
        if path.suffix == ".json" and "status_in_pool" in path.read_text(encoding="utf-8"):
            fail(f"public/ contains a pool record: {rel}")
    print("OK public/: no pool JSONL or status_in_pool records")


def main() -> None:
    try:
        from card_times import self_check as check_card_times
        from migrate_cards import check_shift_slots
    except ImportError:
        from scripts.card_times import self_check as check_card_times
        from scripts.migrate_cards import check_shift_slots
    check_card_times()
    check_shift_slots()
    check_prompt_injection()
    check_schema()
    check_published_schemas()
    check_monotonic()
    check_feed()
    check_rss_escape()
    check_practice()
    check_atlas()
    check_practice_handles()
    check_private_surface()
    check_derive_ignores_pool()
    check_public_excludes_pool()
    try:
        from ingest_x import self_check as check_ingest_x
        from pool_trace import live_report, self_check as check_pool_trace
    except ImportError:
        from scripts.ingest_x import self_check as check_ingest_x
        from scripts.pool_trace import live_report, self_check as check_pool_trace
    check_ingest_x()
    try:
        from shift_ingest_x_to_pool import self_check as check_shift_x
    except ImportError:
        from scripts.shift_ingest_x_to_pool import self_check as check_shift_x
    check_shift_x()
    try:
        from annotate_gates import self_check as check_gates
        from ingest_rss import self_check as check_rss
    except ImportError:
        from scripts.annotate_gates import self_check as check_gates
        from scripts.ingest_rss import self_check as check_rss
    check_gates()
    check_rss()
    try:
        from score_pool import self_check as check_score_pool
        from derive_briefs import self_check as check_derive_briefs
        from fetch_x_watch import self_check as check_fetch_x
        from score_sources import self_check as check_score_sources
    except ImportError:
        from scripts.score_pool import self_check as check_score_pool
        from scripts.derive_briefs import self_check as check_derive_briefs
        from scripts.fetch_x_watch import self_check as check_fetch_x
        from scripts.score_sources import self_check as check_score_sources
    check_score_pool()
    try:
        from force_p0 import self_check as check_force_p0
        from card_copy import self_check as check_card_copy
        from score_pool_v2 import self_check as check_score_v2
        from backtest_score_ab import self_check as check_backtest
        from feishu_notify import self_check as check_feishu
    except ImportError:
        from scripts.force_p0 import self_check as check_force_p0
        from scripts.card_copy import self_check as check_card_copy
        from scripts.score_pool_v2 import self_check as check_score_v2
        from scripts.backtest_score_ab import self_check as check_backtest
        from scripts.feishu_notify import self_check as check_feishu
    check_force_p0()
    check_card_copy()
    check_score_v2()
    check_backtest()
    check_feishu()
    check_derive_briefs()
    check_fetch_x()
    check_score_sources()
    try:
        from editorial_zh import self_check as check_editorial
        from lanes import self_check as check_lanes
        from project_public_lanes import self_check as check_project_lanes
    except ImportError:
        from scripts.editorial_zh import self_check as check_editorial
        from scripts.lanes import self_check as check_lanes
        from scripts.project_public_lanes import self_check as check_project_lanes
    check_editorial()
    check_lanes()
    check_project_lanes()
    try:
        from suggest_atlas_topics import self_check as check_suggest_topics
        from refresh_demand import self_check as check_refresh_demand
    except ImportError:
        from scripts.suggest_atlas_topics import self_check as check_suggest_topics
        from scripts.refresh_demand import self_check as check_refresh_demand
    check_suggest_topics()
    check_refresh_demand()
    check_blog()
    check_topic_suggestions()
    check_briefs()
    check_public_copy()
    check_pool_workflows()
    check_pool_trace()
    live_report()
    check_public_ui()
    try:
        from ops_retract import self_check as check_ops_retract
    except ImportError:
        from scripts.ops_retract import self_check as check_ops_retract
    if check_ops_retract() != 0:
        fail("ops retract/pause dry-run self-check failed")
    check_csp()
    check_beacon()
    check_safe_href()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
