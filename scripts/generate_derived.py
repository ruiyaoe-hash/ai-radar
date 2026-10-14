#!/usr/bin/env python3
"""Derive board artifacts from public/archive (single source of truth).

Reads public/archive and, for the practice lane, public/practice/inbox.
Those are the only inputs. Does not read or write a candidate pool, and does not score.
Pages output stays the promoted public artifacts.

Writes into public/ only:
  - items.json          (rolling window)
  - archive/index.json
  - feed.xml            (main RSS; guid = event id permalink)
  - feeds/lens-*.xml    (per-lens feeds)
  - tools-radar.json    (tools with tool_radar / lens=工具)
  - today3.txt          (今天先做这 3 件，纯文本，页面叫法)
  - practice.json       (only when public/practice/inbox/*.json has items)
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
else:
    from .card_times import parse_source_timestamp

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
            items.append(it)
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
    lines = [f"AI Radar · 今天先做这 3 件（{today}）", ""]
    for i, it in enumerate(picked, 1):
        lines.append(f"{i}. {it.get('title', '')}")
        so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
        impact = str(so.get("impact") or "").strip()
        if not impact:
            jud = list(it.get("judgment") or [])
            obj = objective_lines(it)
            impact = jud[0] if jud else (obj[0] if obj else "")
        if impact:
            lines.append(f"   对你意味着什么：{impact}")
        suggest = " · ".join(
            str(so[k]).strip() for k in ("action", "window") if str(so.get(k) or "").strip()
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
        by_id[eid] = it
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

    print(f"derived: {len(all_items)} archive cards → {len(board)} board items")
    print(f"  items.json, feed.xml, feeds/lens-*.xml, tools-radar.json, today3.txt, archive/index.json")


if __name__ == "__main__":
    main()
