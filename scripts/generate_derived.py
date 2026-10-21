#!/usr/bin/env python3
"""Derive board artifacts from public/archive (single source of truth).

Reads public/archive, public/practice/inbox, public/data/atlas.source.json,
and public/data/demand.json when that roll file exists. Does not read or write
a candidate pool, and does not score.
Pages output stays the promoted public artifacts.

L2 briefs are filled by scripts/derive_briefs.py, not here. One URL is not both an
archive card and a brief. The auto lane never writes the practice inbox; verified
practice stays manual.

Writes into public/ only:
  - items.json          (rolling window)
  - archive/index.json
  - feed.xml            (main RSS; guid = event id permalink)
  - feeds/lens-*.xml    (per-lens feeds)
  - tools-radar.json    (tools with tool_radar / lens=工具)
  - today3.txt          (今日精选，纯文本，页面叫法)
  - practice.json       (only when public/practice/inbox/*.json has items)
  - data/kb.json        (atlas.source.json + practice ids → topics, sources, creators)
  - data/tracks.json, data/topics.json, data/sources.json, data/creators.json
  - topics/<slug>.html  (one static page per atlas topic)

today3 keeps the line labels the homepage parser expects
(「对你意味着什么」「建议」). Spoken wording comes from the card.
Machine ids are stripped. See scripts/human_layer.py.

Public JSON uses the edited objective / so_what / title. Raw social-post
keys (text, full_text, snippet, and the other names in prompt_guard) are
removed before write. The private pool may keep those fields.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import parse_source_timestamp
    from human_layer import strip_machine_ids
    from prompt_guard import strip_raw_post_fields
else:
    from .card_times import parse_source_timestamp
    from .human_layer import strip_machine_ids
    from .prompt_guard import strip_raw_post_fields

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
FEEDS = PUBLIC / "feeds"
SITE = "https://ruiyaoe-hash.github.io/ai-radar/"
TZ = timezone(timedelta(hours=8))
WINDOW_DAYS = 7
MAX_ITEMS = 50
LENSES = ["工具", "赛道", "模式", "时机"]
LENS_LABEL = {
    "工具": "试用工具",
    "赛道": "行业动态",
    "模式": "方法模式",
    "时机": "时机窗口",
}
ROLE_LABEL = {"primary": "一手", "analysis": "解读", "report": "转述"}
TOOL_RING_LABEL = {
    "采纳": "值得用上",
    "试用": "可以试",
    "评估": "先评估",
    "暂缓": "先别跟",
}


def esc(t: str) -> str:
    return html.escape(t or "", quote=True)


def safe_http_url(url: object) -> str:
    """Absolute http(s) only. Reject javascript:, data:, and protocol-relative URLs.

    Feed links are absolute. Relative paths stay on the HTML pages, not in RSS.
    Hosts are not filtered: HN, Reddit, GitHub, and lab blogs are all valid.
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    if any(c.isspace() or ord(c) < 32 or c in '<>"\'`\\' for c in raw):
        return ""
    if raw.startswith("//"):
        return ""
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return raw


def feed_item_link(it: dict) -> str:
    chosen = safe_http_url(it.get("url") or "")
    if chosen:
        return chosen
    fallback = safe_http_url(event_permalink(it))
    if fallback:
        return fallback
    return SITE


def rss_html_description(desc_html: str) -> str:
    """Card fields are HTML-escaped before this join. Trusted tags are only <strong> and <br/>.

    html.escape encodes '>', so a card cannot close the CDATA section with ']]>'.
    A leftover terminator or a raw <script means a field skipped escaping.
    """
    if "]]>" in desc_html or "<script" in desc_html.lower():
        raise ValueError("RSS description has an unescaped HTML payload")
    return desc_html


def load_all_archive_items() -> list[dict]:
    items: list[dict] = []
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items", []):
            # Archive files stay as committed. Derived copies drop raw post bodies.
            items.append(strip_raw_post_fields(it))
    return items


def parse_item_time(it: dict) -> datetime:
    """Board/RSS order. Prefer published_at when the card has a real source clock.

    Does not invent published_at. Cards without it keep the Beijing display clock
    (`date` + `time`), then noon on `date` only.
    """
    published = parse_source_timestamp(it.get("published_at"))
    if published:
        return datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(TZ)
    now = datetime.now(TZ)
    date = (it.get("date") or "").strip()
    time_s = (it.get("time") or "").strip()
    try:
        if date and time_s and " " in time_s:
            hm = time_s.split(" ", 1)[1]
            hh, mi = hm.split(":")
            y, m, d = date.split("-")
            return datetime(int(y), int(m), int(d), int(hh), int(mi), tzinfo=TZ)
        if date:
            y, m, d = date.split("-")
            return datetime(int(y), int(m), int(d), 12, 0, tzinfo=TZ)
    except Exception:
        pass
    return now


def event_permalink(it: dict) -> str:
    eid = it.get("id") or ""
    if eid:
        return f"{SITE}#/{eid}"
    return it.get("url") or SITE


def objective_lines(it: dict) -> list[str]:
    return list(it.get("objective") or [])


def public_band(it: dict) -> str:
    """Page label for priority. P0 rumor/pending → 市场信号; other P0 → 今日必看; P1 → 重点关注."""
    if it.get("priority") == "P0" and (
        it.get("status") == "rumor" or it.get("pending") in (True, "pending", "rumor")
    ):
        return "市场信号"
    if it.get("priority") == "P0":
        return "今日必看"
    if it.get("priority") == "P1":
        return "重点关注"
    return ""


def build_rss(items: list[dict], title: str, description: str, self_url: str) -> str:
    now = datetime.now(TZ)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{esc(title)}</title>",
        f"<link>{esc(SITE)}</link>",
        f"<description>{esc(description)}</description>",
        "<language>zh-cn</language>",
        f"<lastBuildDate>{esc(format_datetime(now))}</lastBuildDate>",
        f'<atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>',
    ]
    for it in items:
        band = public_band(it)
        lens = LENS_LABEL.get(it.get("lens") or "", "")
        tag = it.get("tag") or ""
        bits = [b for b in (band, lens, tag) if b]
        prefix = f"[{' · '.join(bits)}] " if bits else ""
        title_s = f"{prefix}{it.get('title', '')}"
        link = feed_item_link(it)
        guid = event_permalink(it)
        obj = objective_lines(it)
        jud = list(it.get("judgment") or [])
        label = it.get("judgment_label") or "判断"
        desc_parts = []
        if obj:
            desc_parts.append("<strong>背景</strong>")
            desc_parts.extend(f"• {esc(b)}" for b in obj)
        so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
        if so.get("falsifier"):
            if so.get("impact"):
                desc_parts.append(f"<strong>对你意味着什么</strong> {esc(str(so['impact']))}")
            suggest = " · ".join(
                str(so[k]) for k in ("action", "window") if so.get(k)
            )
            if suggest:
                desc_parts.append(f"建议：{esc(suggest)}")
            if so.get("confidence"):
                desc_parts.append(f"有多确定：{esc(str(so['confidence']))}")
            desc_parts.append(f"什么情况下当这判断作废：{esc(str(so['falsifier']))}")
        elif jud:
            desc_parts.append(f"<strong>{esc(label)}</strong>")
            desc_parts.extend(f"• {esc(b)}" for b in jud)
        if it.get("correction"):
            c = it["correction"]
            note = c.get("note") if isinstance(c, dict) else str(c)
            desc_parts.append(f"<strong>更正</strong> {esc(note or '')}")
        handles = ", ".join(
            f"{esc(s.get('handle', ''))}（{esc(ROLE_LABEL.get(s.get('role', ''), s.get('role', '')))}）"
            for s in (it.get("sources") or [])
        )
        if handles:
            desc_parts.append(f"来源 {handles}")
        if it.get("date"):
            desc_parts.append(f"日期 {esc(it['date'])}")
        desc = rss_html_description("<br/>".join(desc_parts))
        pub = parse_item_time(it)
        parts += [
            "<item>",
            f"<title>{esc(title_s)}</title>",
            f"<link>{esc(link)}</link>",
            f'<guid isPermaLink="false">{esc(it.get("id") or guid)}</guid>',
            f"<pubDate>{esc(format_datetime(pub))}</pubDate>",
            f"<description><![CDATA[{desc}]]></description>",
            "</item>",
        ]
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def write_archive_index(all_items: list[dict]) -> None:
    counts: dict[str, int] = {}
    for it in all_items:
        d = it.get("date") or ""
        if d:
            counts[d] = counts.get(d, 0) + 1
    dates = [{"date": d, "count": counts[d]} for d in sorted(counts.keys(), reverse=True)]
    (ARCHIVE / "index.json").write_text(
        json.dumps({"dates": dates}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def board_window(all_items: list[dict]) -> list[dict]:
    if not all_items:
        return []
    dates = sorted({it.get("date") for it in all_items if it.get("date")}, reverse=True)
    if not dates:
        return sorted(all_items, key=parse_item_time, reverse=True)[:MAX_ITEMS]
    cutoff = dates[0]
    try:
        y, m, d = map(int, cutoff.split("-"))
        start = datetime(y, m, d, tzinfo=TZ) - timedelta(days=WINDOW_DAYS - 1)
        start_s = start.strftime("%Y-%m-%d")
    except Exception:
        start_s = dates[-1]
    window = [it for it in all_items if (it.get("date") or "") >= start_s]
    window.sort(key=parse_item_time, reverse=True)
    return window[:MAX_ITEMS]


def build_tools_radar(all_items: list[dict]) -> dict:
    rings = {"采纳": [], "试用": [], "评估": [], "暂缓": []}
    for it in all_items:
        if it.get("lens") != "工具" and not it.get("tool_radar"):
            continue
        ring = it.get("tool_radar") or "评估"
        if ring not in rings:
            ring = "评估"
        rings[ring].append({
            "id": it.get("id"),
            "title": it.get("title"),
            "date": it.get("date"),
            "try_url": it.get("try_url") or it.get("url"),
            "access": it.get("access"),
            "integration": it.get("integration"),
            "first_step": it.get("first_step"),
            "alternatives": it.get("alternatives") or [],
            "status": it.get("status"),
            "priority": it.get("priority"),
        })
    return {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
        "rings": rings,
        "note": "按你现在该怎么对待来分："
        + "、".join(TOOL_RING_LABEL[k] for k in ("采纳", "试用", "评估", "暂缓"))
        + "。不按热度排。",
    }


def build_today3(board: list[dict]) -> str:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    day_items = [it for it in board if it.get("date") == today]
    if not day_items:
        day_items = board[:3]
    # prefer P0 then confirmed
    def score(it):
        p = 0 if it.get("priority") == "P0" else 1
        s = 0 if it.get("status") == "confirmed" else (1 if it.get("status") == "multi_source" else 2)
        return (p, s, -(parse_item_time(it).timestamp()))

    picked = sorted(day_items, key=score)[:3]
    lines = [f"AI Radar · 今日精选（{today}）", ""]
    for i, it in enumerate(picked, 1):
        title = strip_machine_ids(str(it.get("title") or ""))
        lines.append(f"{i}. {title}")
        so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
        impact = strip_machine_ids(str(so.get("impact") or ""))
        if not impact:
            jud = list(it.get("judgment") or [])
            obj = objective_lines(it)
            impact = strip_machine_ids(jud[0] if jud else (obj[0] if obj else ""))
        if impact:
            lines.append(f"   对你意味着什么：{impact}")
        suggest = " · ".join(
            strip_machine_ids(str(so.get(k) or ""))
            for k in ("action", "window")
            if str(so.get(k) or "").strip()
        )
        if suggest:
            lines.append(f"   建议：{suggest}")
        if it.get("url"):
            lines.append(f"   {it['url']}")
        lines.append("")
    lines.append(f"看板 {SITE}")
    return "\n".join(lines).rstrip() + "\n"


def _practice_items(payload) -> list[dict]:
    if isinstance(payload, list):
        return [it for it in payload if isinstance(it, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return [it for it in payload["items"] if isinstance(it, dict)]
        if payload.get("id"):
            return [payload]
    raise ValueError("practice inbox entry must be an item, a list, or {items: []}")


PRACTICE_NOTE = "编辑精选、每周投放，非自动从监控信源捞取。"


def sync_practice_inbox() -> None:
    """Merge public/practice/inbox/*.json into practice.json.

    Inbox JSON only. This is not a private checkout and not a score input.
    Empty inbox leaves the committed file alone (the page then shows an empty state).
    Sample cards live in practice.sample.json and are not published here.
    Optional editorial fields (difficulty, prerequisites, estimated_time, verified)
    are copied through unchanged.
    """
    inbox = PUBLIC / "practice" / "inbox"
    incoming: list[dict] = []
    if inbox.is_dir():
        for path in sorted(inbox.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"practice inbox {path.name}: {exc}") from exc
            try:
                incoming.extend(_practice_items(payload))
            except ValueError as exc:
                raise SystemExit(f"practice inbox {path.name}: {exc}") from exc
    dest = PUBLIC / "practice.json"
    if not incoming:
        if not dest.exists():
            dest.write_text(
                json.dumps(
                    {"schema_version": 1, "updated": None, "items": []},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return
    existing: list[dict] = []
    if dest.exists():
        try:
            doc = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"practice.json: {exc}") from exc
        existing = [it for it in (doc.get("items") or []) if isinstance(it, dict)]
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for it in existing + incoming:
        eid = str(it.get("id") or "")
        if not eid:
            raise SystemExit("practice item missing id")
        if eid not in by_id:
            order.append(eid)
        by_id[eid] = strip_raw_post_fields(it)
    items = [by_id[eid] for eid in order]
    items.sort(key=lambda it: str(it.get("time") or ""), reverse=True)
    dest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
                "note": PRACTICE_NOTE,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"  practice.json: {len(items)} items ({len(incoming)} from inbox)")


ATLAS_SOURCE = PUBLIC / "data" / "atlas.source.json"
TOPICS_DIR = PUBLIC / "topics"
ATLAS_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://static.cloudflareinsights.com; "
    "script-src-attr 'none'; "
    "style-src 'self'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self' https://cloudflareinsights.com; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-src 'none'"
)


def _dump_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _metric(value):
    """Integer engagement count. Booleans are not counts."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _write_topic_pages(topics: list[dict]) -> None:
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    slugs: list[str] = []
    for topic in topics:
        slug = str(topic.get("slug") or "")
        if not slug:
            raise SystemExit("atlas topic missing slug")
        slugs.append(slug)
        title = html.escape(str(topic.get("name") or slug), quote=True)
        safe_slug = html.escape(slug, quote=True)
        page = f"""<!DOCTYPE html>
<html lang="zh-CN" data-page="atlas" data-root="../" data-slug="{safe_slug}">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="{ATLAS_CSP}" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="theme-color" content="#0c0e12" />
  <title>{title} · AI Radar</title>
  <link rel="icon" href="../assets/logo.png" />
  <link rel="stylesheet" href="../assets/radar.css" />
</head>
<body>
  <div class="app">
    <script src="../assets/safe-href.js"></script>
    <script src="../assets/shell.js"></script>
    <div class="content">
      <div class="topbar">
        <button class="menu-btn" type="button" data-nav-open>菜单</button>
        <span class="topbar-title">{title}</span>
      </div>
      <main class="wide">
        <div id="topic-root">
          <p class="empty">正在读取这个主题…</p>
        </div>
        <footer class="site-footer">
          <p>内容摘自公开帖子与编辑整理的实操，版权归原作者所有。点击来源可查看原文。</p>
          <p>内容可能包含未经证实的传闻与第三方帖子，请自行核对。</p>
          <p>更正与下架：请通过「<a href="https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。</p>
        </footer>
      </main>
    </div>
  </div>
  <script src="../assets/atlas.js"></script>
</body>
</html>
"""
        (TOPICS_DIR / f"{slug}.html").write_text(page, encoding="utf-8")
    for path in TOPICS_DIR.glob("*.html"):
        if path.stem not in slugs:
            path.unlink()


def _load_demand() -> dict | None:
    path = PUBLIC / "data" / "demand.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"demand.json: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("demand.json: expected an object")
    return data


def _overlay_demand(source: dict, rolled: dict) -> dict:
    extra = rolled.get(str(source.get("id") or ""))
    if not isinstance(extra, dict):
        return source
    out = dict(source)
    for key in ("likes", "bookmarks", "views"):
        value = extra.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        out[key] = value
    origin = extra.get("from")
    if origin in {"atlas", "archive", "pool", "demand"}:
        out["demand_from"] = origin
    observed = extra.get("observed_at")
    if isinstance(observed, str) and observed:
        out["demand_observed_at"] = observed
    return out


def sync_atlas() -> None:
    """Publish the topic atlas from public/data/atlas.source.json.

    Every live practice id must already be a source (origin=practice).
    Counts, the smoothed demand signal, creator rank, and topics/<slug>.html
    are derived. data/demand.json overlays newer bookmark/like counts.
    verified on a practice source is copied from practice.json, not invented.
    """
    if not ATLAS_SOURCE.is_file():
        print("  atlas: no data/atlas.source.json, skip")
        return
    try:
        raw = json.loads(ATLAS_SOURCE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"atlas.source.json: {exc}") from exc
    src = strip_raw_post_fields(raw)
    sources = [item for item in (src.get("sources") or []) if isinstance(item, dict)]
    seen: set[str] = set()
    for source in sources:
        sid = str(source.get("id") or "")
        if not sid:
            raise SystemExit("atlas source missing id")
        if sid in seen:
            raise SystemExit(f"atlas duplicate source id {sid}")
        seen.add(sid)
    practice_ids: list[str] = []
    verified_by_id: dict[str, bool] = {}
    practice_path = PUBLIC / "practice.json"
    if practice_path.is_file():
        try:
            doc = json.loads(practice_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"practice.json: {exc}") from exc
        for item in doc.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                practice_ids.append(str(item["id"]))
                verified_by_id[str(item["id"])] = item.get("verified") is True
    missing = [pid for pid in practice_ids if pid not in seen]
    if missing:
        raise SystemExit(
            "atlas.source.json missing practice ids "
            f"(map each inbox card onto a topic): {missing}"
        )
    demand = _load_demand()
    rolled = (demand or {}).get("sources") if isinstance((demand or {}).get("sources"), dict) else {}
    sources = [_overlay_demand(source, rolled) for source in sources]
    for source in sources:
        if source.get("origin") == "practice":
            source["verified"] = verified_by_id.get(str(source.get("id") or ""), False)
    refreshed_label = str((demand or {}).get("refreshed_label") or "")
    refreshed_utc = str((demand or {}).get("refreshed_at") or "")
    formula = str((demand or {}).get("formula") or "")
    from refresh_demand import topic_save_ratio
    from score_pool import load_score_config

    score_cfg = load_score_config(ROOT)
    topics_in = [item for item in (src.get("topics") or []) if isinstance(item, dict)]
    slug_set = {str(item.get("slug") or "") for item in topics_in}
    by_topic: dict[str, list[dict]] = {}
    for source in sources:
        topic_slug = str(source.get("topic") or "")
        if topic_slug not in slug_set:
            raise SystemExit(f"{source.get('id')} topic {topic_slug} is not a known slug")
        by_topic.setdefault(topic_slug, []).append(source)
    topics_out: list[dict] = []
    for topic in topics_in:
        slug = str(topic.get("slug") or "")
        items = by_topic.get(slug, [])
        authors: list[str] = []
        for source in items:
            author = str(source.get("author") or "")
            if author and author not in authors:
                authors.append(author)
        measured = [
            source for source in items
            if _metric(source.get("likes")) is not None and _metric(source.get("bookmarks")) is not None
        ]
        has_bookmarks = any(_metric(source.get("bookmarks")) is not None for source in items)
        dates = sorted(str(source.get("date") or "") for source in items if source.get("date"))
        for step in topic.get("playbook") or []:
            if not isinstance(step, dict):
                continue
            for sid in step.get("sources") or []:
                if sid not in seen:
                    raise SystemExit(f"{slug} playbook cites missing source {sid}")
        enriched = dict(topic)
        enriched["status"] = "待采集" if not items else "active"
        enriched["source_count"] = len(items)
        enriched["creator_count"] = len(authors)
        enriched["has_bookmarks"] = has_bookmarks
        if has_bookmarks:
            enriched["bookmarks"] = sum(_metric(source.get("bookmarks")) or 0 for source in items)
            enriched["likes"] = sum(_metric(source.get("likes")) or 0 for source in items)
        else:
            enriched.pop("bookmarks", None)
            enriched.pop("likes", None)
        samples = [
            (_metric(source.get("bookmarks")) or 0, _metric(source.get("likes")) or 0)
            for source in measured
        ]
        ratio = topic_save_ratio(
            samples,
            score_cfg.bookmark_prior,
            score_cfg.like_prior,
            score_cfg.author_prior_n,
        )
        if ratio is None:
            enriched.pop("save_ratio", None)
        else:
            enriched["save_ratio"] = ratio
        enriched["demand_samples"] = len(samples)
        enriched["unverified_practice"] = sum(
            1 for source in items if source.get("origin") == "practice" and source.get("verified") is not True
        )
        enriched["verified_practice"] = sum(
            1 for source in items if source.get("origin") == "practice" and source.get("verified") is True
        )
        if refreshed_label:
            enriched["demand_refreshed_at"] = refreshed_label
        if dates:
            enriched["latest"] = dates[-1]
        else:
            enriched.pop("latest", None)
        topics_out.append(enriched)

    known: dict[str, dict] = {}
    for creator in src.get("creators") or []:
        if isinstance(creator, dict) and creator.get("handle"):
            known[str(creator["handle"])] = creator
    handles: list[str] = []
    for source in sources:
        author = str(source.get("author") or "")
        if author and author not in handles:
            handles.append(author)
    creator_rows: list[dict] = []
    for handle in handles:
        base = dict(known.get(handle) or {"handle": handle, "name": handle, "focus": ""})
        posts = [source for source in sources if source.get("author") == handle]
        topic_ids: list[str] = []
        for source in posts:
            topic_slug = str(source.get("topic") or "")
            if topic_slug and topic_slug not in topic_ids:
                topic_ids.append(topic_slug)
        base["source_count"] = len(posts)
        base["bookmarks"] = sum(_metric(source.get("bookmarks")) or 0 for source in posts)
        base["bookmark_metric"] = any(_metric(source.get("bookmarks")) is not None for source in posts)
        base["topics"] = topic_ids
        if not str(base.get("profile_url") or "").strip():
            base["profile_url"] = f"https://x.com/{handle}"
        creator_rows.append(base)

    def _rank(creator: dict):
        primary = creator["bookmarks"] if creator.get("bookmark_metric") else creator["source_count"]
        return (-int(primary), -int(creator["source_count"]), str(creator.get("handle") or ""))

    creator_rows.sort(key=_rank)
    tracks = [item for item in (src.get("tracks") or []) if isinstance(item, dict)]
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间")
    payload = {
        "schema_version": 1,
        "snapshot": src.get("snapshot") or "2026-10-20",
        "updated": now,
        "note": src.get("note") or "",
        "tracks": tracks,
        "topics": topics_out,
        "sources": sources,
        "creators": creator_rows,
    }
    if refreshed_label:
        payload["demand_refreshed_at"] = refreshed_label
        payload["demand_refreshed_at_utc"] = refreshed_utc
        payload["demand_formula"] = formula
    kb = strip_raw_post_fields(payload)
    data = PUBLIC / "data"
    _dump_json(data / "kb.json", kb)
    _dump_json(data / "tracks.json", {"schema_version": 1, "updated": now, "tracks": tracks})
    _dump_json(data / "topics.json", {"schema_version": 1, "updated": now, "topics": topics_out})
    _dump_json(data / "sources.json", {"schema_version": 1, "updated": now, "sources": sources})
    _dump_json(data / "creators.json", {"schema_version": 1, "updated": now, "creators": creator_rows})
    _write_topic_pages(topics_out)
    print(f"  atlas: {len(topics_out)} topics, {len(sources)} sources, {len(creator_rows)} creators")


def main():
    FEEDS.mkdir(parents=True, exist_ok=True)
    all_items = load_all_archive_items()
    write_archive_index(all_items)
    board = board_window(all_items)
    now = datetime.now(TZ)
    items_doc = {
        "schema_version": 2,
        "updated": now.strftime("%Y-%m-%d %H:%M 北京时间"),
        "window_note": "看板展示近几日信号（约 7 天 / 最多约 50 条）；更早日期见本周归档。",
        "items": board,
    }
    (PUBLIC / "items.json").write_text(
        json.dumps(items_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    (PUBLIC / "feed.xml").write_text(
        build_rss(
            board,
            "AI Radar",
            "会影响下一步的信号。北京时间每天 08:00 主报；工作日 21:00 晚班。",
            SITE + "feed.xml",
        ),
        encoding="utf-8",
    )

    for lens in LENSES:
        lens_items = [it for it in board if it.get("lens") == lens]
        slug = {"工具": "tools", "赛道": "tracks", "模式": "models", "时机": "timing"}[lens]
        label = LENS_LABEL[lens]
        (FEEDS / f"lens-{slug}.xml").write_text(
            build_rss(
                lens_items,
                f"AI Radar · {label}",
                f"只看{label}。",
                SITE + f"feeds/lens-{slug}.xml",
            ),
            encoding="utf-8",
        )

    radar = build_tools_radar(all_items)
    (PUBLIC / "tools-radar.json").write_text(
        json.dumps(radar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (PUBLIC / "today3.txt").write_text(build_today3(board), encoding="utf-8")
    sync_practice_inbox()
    sync_atlas()

    print(f"derived: {len(all_items)} archive cards → {len(board)} board items")
    print(f"  items.json, feed.xml, feeds/lens-*.xml, tools-radar.json, today3.txt, archive/index.json")


if __name__ == "__main__":
    main()
