#!/usr/bin/env python3
"""Derive board artifacts from public/archive (single source of truth).

Writes into public/ only:
  - items.json          (rolling window)
  - archive/index.json
  - feed.xml            (main RSS; guid = event id permalink)
  - feeds/lens-*.xml    (per-lens feeds)
  - tools-radar.json    (tools with tool_radar / lens=工具)
  - today3.txt          (今日3条 plain text for copy)
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
FEEDS = PUBLIC / "feeds"
SITE = "https://ruiyaoe-hash.github.io/ai-radar/"
TZ = timezone(timedelta(hours=8))
WINDOW_DAYS = 7
MAX_ITEMS = 50
LENSES = ["工具", "赛道", "模式", "时机"]


def esc(t: str) -> str:
    return html.escape(t or "", quote=True)


def load_all_archive_items() -> list[dict]:
    items: list[dict] = []
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items", []):
            items.append(it)
    return items


def parse_item_time(it: dict) -> datetime:
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
        prio = it.get("priority", "")
        status = it.get("status", "")
        pending = prio == "P0" and status == "rumor"
        prio_label = "P0-待证" if pending else prio
        lens = it.get("lens") or ""
        tag = it.get("tag") or ""
        title_s = f"[{prio_label}/{lens}/{tag}] {it.get('title', '')}"
        link = it.get("url") or event_permalink(it)
        guid = event_permalink(it)
        obj = objective_lines(it)
        jud = list(it.get("judgment") or [])
        label = it.get("judgment_label") or "主观判断"
        desc_parts = []
        if obj:
            desc_parts.append("<strong>客观摘要</strong>")
            desc_parts.extend(f"• {esc(b)}" for b in obj)
        so = it.get("so_what")
        if isinstance(so, dict) and so.get("falsifier"):
            desc_parts.append("<strong>【so_what】</strong>")
            for k in ("impact", "action", "window", "confidence", "falsifier", "thesis_id"):
                if so.get(k):
                    desc_parts.append(f"• {esc(k)}: {esc(str(so[k]))}")
        elif jud:
            desc_parts.append(f"<strong>【{esc(label)}】</strong>")
            desc_parts.extend(f"• {esc(b)}" for b in jud)
        if it.get("correction"):
            c = it["correction"]
            note = c.get("note") if isinstance(c, dict) else str(c)
            desc_parts.append(f"<strong>【更正】</strong> {esc(note or '')}")
        handles = ", ".join(
            f"@{esc(s.get('handle', ''))}({esc(s.get('role', ''))})"
            for s in (it.get("sources") or [])
        )
        if handles:
            desc_parts.append(f"来源 {handles}")
        if it.get("date"):
            desc_parts.append(f"日期 {esc(it['date'])}")
        desc = "<br/>".join(desc_parts)
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
        "note": "Tech Radar：采纳 / 试用 / 评估 / 暂缓。主人可在归档卡上写 tool_radar 字段。",
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
    lines = [f"AI Radar · 今日3条（{today}）", ""]
    for i, it in enumerate(picked, 1):
        prio = it.get("priority", "")
        pending = prio == "P0" and it.get("status") == "rumor"
        pl = "P0-待证" if pending else prio
        lines.append(f"{i}. [{pl}/{it.get('lens','')}] {it.get('title','')}")
        obj = objective_lines(it)
        if obj:
            lines.append(f"   · {obj[0]}")
        if it.get("url"):
            lines.append(f"   {it['url']}")
        lines.append("")
    lines.append(f"看板 {SITE}")
    return "\n".join(lines).rstrip() + "\n"


def main():
    FEEDS.mkdir(parents=True, exist_ok=True)
    all_items = load_all_archive_items()
    write_archive_index(all_items)
    board = board_window(all_items)
    now = datetime.now(TZ)
    items_doc = {
        "schema_version": 2,
        "updated": now.strftime("%Y-%m-%d %H:%M 北京时间"),
        "window_note": "看板展示近几日精选（约 7 天 / 最多约 50 条）；更早日期见归档。主过滤按 lens。",
        "items": board,
    }
    (PUBLIC / "items.json").write_text(
        json.dumps(items_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    (PUBLIC / "feed.xml").write_text(
        build_rss(
            board,
            "AI Radar · Decision Signal",
            "决策信号：事件模型 + lens 过滤。客观摘要与 so_what/主观判断分栏。",
            SITE + "feed.xml",
        ),
        encoding="utf-8",
    )

    for lens in LENSES:
        lens_items = [it for it in board if it.get("lens") == lens]
        slug = {"工具": "tools", "赛道": "tracks", "模式": "models", "时机": "timing"}[lens]
        (FEEDS / f"lens-{slug}.xml").write_text(
            build_rss(
                lens_items,
                f"AI Radar · lens={lens}",
                f"仅 lens={lens} 的决策信号",
                SITE + f"feeds/lens-{slug}.xml",
            ),
            encoding="utf-8",
        )

    radar = build_tools_radar(all_items)
    (PUBLIC / "tools-radar.json").write_text(
        json.dumps(radar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (PUBLIC / "today3.txt").write_text(build_today3(board), encoding="utf-8")

    print(f"derived: {len(all_items)} archive cards → {len(board)} board items")
    print(f"  items.json, feed.xml, feeds/lens-*.xml, tools-radar.json, today3.txt, archive/index.json")


if __name__ == "__main__":
    main()
