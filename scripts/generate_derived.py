#!/usr/bin/env python3
"""Derive board artifacts from public/archive (single source of truth).

Reads public/archive, public/practice/inbox, public/data/atlas.source.json,
and public/data/demand.json when that roll file exists. Does not read or write
a candidate pool, and does not score.
Pages output stays the promoted public artifacts.

L2 briefs are filled by scripts/derive_briefs.py, not here. One URL is not both an
archive card and a brief. Practice cards arrive from public/practice/inbox.
scripts/project_public_lanes.py is the only writer of that inbox.

Writes into public/ only:
  - items.json          (rolling window)
  - archive/index.json
  - feed.xml            (main RSS; guid = event id permalink)
  - feeds/lens-*.xml    (per-lens feeds)
  - tools-radar.json    (tools with tool_radar / lens=工具)
  - today3.txt          (信息精选里最新一天的纯文本)
  - picks.json          (信息精选：硬门槛每天最多 3 条；空天只顶一条工具或简讯)
  - practice.json       (only when public/practice/inbox/*.json has items)
  - data/kb.json        (atlas.source.json + practice ids → topics, sources, creators)
  - data/tracks.json, data/topics.json, data/sources.json, data/creators.json
  - topics/<slug>.html  (one static page per atlas topic)
  - blog/               (content/posts/*.md via scripts/build_blog.py)

today3 keeps the line labels the homepage parser expects
(「对你意味着什么」「建议」). Spoken wording comes from the card.
Machine ids are stripped. See scripts/human_layer.py.

Public JSON uses the edited objective / so_what / title. Raw social-post
keys (text, full_text, snippet, and the other names in prompt_guard) are
removed before write. The private pool may keep those fields.
"""
from __future__ import annotations

import copy
import html
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_blog import build as build_blog
    from card_times import parse_source_timestamp
    from human_layer import strip_machine_ids
    from prompt_guard import strip_raw_post_fields
    from editorial_zh import visitor_ready
    from lanes import (
        PER_DAY,
        fill_empty_pick_days,
        identity_ids,
        identity_urls,
        select_picks,
        without_promoted_briefs,
    )
else:
    from .build_blog import build as build_blog
    from .card_times import parse_source_timestamp
    from .human_layer import strip_machine_ids
    from .prompt_guard import strip_raw_post_fields
    from .editorial_zh import visitor_ready
    from .lanes import (
        PER_DAY,
        fill_empty_pick_days,
        identity_ids,
        identity_urls,
        select_picks,
        without_promoted_briefs,
    )

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
    "工具": "新工具",
    "赛道": "行业动态",
    "模式": "方法模式",
    "时机": "时机窗口",
}
ROLE_LABEL = {"primary": "一手", "analysis": "解读", "report": "转述"}
# Visitor tool states are two labels. Older four-ring values still map.
TOOL_RING_LABEL = {
    "采纳": "推荐使用",
    "试用": "推荐使用",
    "评估": "值得关注",
    "暂缓": "值得关注",
    "值得采用": "推荐使用",
    "可以试用": "推荐使用",
    "需要评估": "值得关注",
    "暂缓跟进": "值得关注",
    "推荐使用": "推荐使用",
    "值得关注": "值得关注",
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
    """Visitor label. Internal priority stays on the card and is not printed as P0."""
    if it.get("priority") == "P0" and (
        it.get("status") == "rumor" or it.get("pending") in (True, "pending", "rumor")
    ):
        return "尚待核实"
    if it.get("priority") == "P0":
        return "重磅"
    if it.get("priority") == "P1":
        return "快讯"
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


STAMP_RE = re.compile(r'^\s*"updated": "[^"]*",?$|<lastBuildDate>[^<]*</lastBuildDate>', re.M)


def write_stable(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Skip the write when only the wall-clock stamp would change, so reruns do not churn git."""
    if path.is_file():
        old = path.read_text(encoding=encoding)
        if old == text or STAMP_RE.sub("", old) == STAMP_RE.sub("", text):
            return
    path.write_text(text, encoding=encoding)


def write_archive_index(all_items: list[dict]) -> None:
    counts: dict[str, int] = {}
    for it in all_items:
        d = it.get("date") or ""
        if d:
            counts[d] = counts.get(d, 0) + 1
    dates = [{"date": d, "count": counts[d]} for d in sorted(counts.keys(), reverse=True)]
    write_stable((ARCHIVE / "index.json"),
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


def _public_sentence(text: object, limit: int = 220) -> str:
    cleaned = strip_machine_ids(str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _tool_record(it: dict, ring: str) -> dict | None:
    objective = it.get("objective") or []
    summary = _public_sentence(objective[0] if objective else it.get("title"))
    so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
    audience = _public_sentence(so.get("impact") or it.get("access") or "")
    experiment = _public_sentence(it.get("first_step") or "", 240)
    title = str(it.get("title") or "").strip()
    if not summary or not audience or not experiment:
        return None
    if not visitor_ready(title) or not visitor_ready(summary) or not visitor_ready(audience) or not visitor_ready(experiment):
        return None
    return {
        "id": it.get("id"),
        "title": it.get("title"),
        "date": it.get("date"),
        "time": it.get("time"),
        "try_url": it.get("try_url") or it.get("url"),
        "access": it.get("access"),
        "integration": it.get("integration"),
        "first_step": experiment,
        "summary": summary,
        "audience_value": audience,
        "alternatives": it.get("alternatives") or [],
        "status": it.get("status"),
        "priority": it.get("priority"),
        "stance": TOOL_RING_LABEL.get(ring, "值得关注"),
    }


def build_tools_radar(all_items: list[dict]) -> dict:
    rings = {
        "推荐使用": [],
        "值得关注": [],
        # Legacy keys stay empty so older readers do not crash. Visitors use the two labels.
        "采纳": [],
        "试用": [],
        "评估": [],
        "暂缓": [],
    }
    stream: list[dict] = []
    for it in all_items:
        if it.get("lens") != "工具" and not it.get("tool_radar"):
            continue
        ring = it.get("tool_radar") or "值得关注"
        if ring not in TOOL_RING_LABEL:
            ring = "值得关注"
        record = _tool_record(it, ring)
        if record is None:
            continue
        visitor = record.get("stance") or "值得关注"
        rings[visitor].append(record)
        stream.append(record)
    # Newest display clock first, matching the published rings. Equal clocks keep
    # archive order so a later regenerate does not flip the whole list.
    order = lambda item: (str(item.get("date") or ""), str(item.get("time") or ""))
    for group in rings.values():
        group.sort(key=order, reverse=True)
    stream.sort(key=order, reverse=True)
    return {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
        "rings": rings,
        "stream": stream,
        "note": "按时间往下看。档位只有推荐使用和值得关注。每条写清摘要、大众价值，以及第一次怎么试。",
    }


def _visitor_card(it: dict) -> bool:
    """A public pick needs a finished Chinese title, fact, and impact."""
    title = str(it.get("title") or "").strip()
    obj = it.get("objective") or it.get("bullets") or []
    happened = str(obj[0] if obj else title).strip()
    so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
    impact = str(so.get("impact") or "").strip()
    if not impact:
        judgment = [str(line).strip() for line in (it.get("judgment") or []) if str(line).strip()]
        impact = judgment[0] if judgment else ""
    return visitor_ready(title) and visitor_ready(happened) and visitor_ready(impact)


_RING_ACTION = {
    "采纳": "推荐使用",
    "试用": "推荐使用",
    "评估": "值得关注",
    "暂缓": "值得关注",
    "推荐使用": "推荐使用",
    "值得关注": "值得关注",
}
# Visitor falsifier for a fact that was lifted onto an empty picks day.
# It does not claim a hard P0, and it does not name the fill machinery.
_BRIEF_FILL_FALSIFIER = "如果原文事后被更正，或者这件事和你这周要做的事对不上，就不必为此改安排。"


def _visitor_stamp(item: dict) -> float:
    raw = item.get("published_at") or item.get("ingested_at") or ""
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    day = str(item.get("date") or "")
    clock = str(item.get("time") or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and " " in clock:
        try:
            hh, mi = clock.split(" ", 1)[1].split(":")
            year, month, dom = (int(part) for part in day.split("-"))
            return datetime(year, month, dom, int(hh), int(mi), tzinfo=TZ).timestamp()
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def _action_labels_for_tool(it: dict, ring: str) -> list[str]:
    labels: list[str] = []
    so = it.get("so_what") if isinstance(it.get("so_what"), dict) else {}
    action = str(so.get("action") or "").strip()
    if action:
        labels.append(action)
    mapped = _RING_ACTION.get(ring)
    if mapped:
        labels.append(mapped)
    copy = it.get("card_copy") if isinstance(it.get("card_copy"), dict) else {}
    suggested = str(copy.get("suggested_action") or "").strip()
    if suggested:
        labels.append(suggested)
    return labels


def _action_labels_for_brief(it: dict) -> list[str]:
    copy = it.get("card_copy") if isinstance(it.get("card_copy"), dict) else {}
    suggested = str(copy.get("suggested_action") or "").strip()
    if suggested in {"立即行动", "持续观察", "暂缓"}:
        return [suggested]
    return ["持续观察"]


def _load_public_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _brief_rows() -> list[dict]:
    data = _load_public_json(PUBLIC / "briefs.json")
    return [item for item in (data.get("items") or []) if isinstance(item, dict)]


def _prior_brief_fills() -> list[dict]:
    """Briefs already lifted into picks. The brief file drops them, so the next
    derive has to read the pick copy or the empty day would go blank again.
    """
    data = _load_public_json(PUBLIC / "picks.json")
    found: list[dict] = []
    for day in data.get("days") or []:
        if not isinstance(day, dict):
            continue
        for item in day.get("items") or []:
            if (
                isinstance(item, dict)
                and item.get("fill_reason") == "empty_day"
                and item.get("promoted_from") == "brief"
            ):
                found.append(item)
    return found


def _brief_pick(item: dict) -> dict | None:
    """Visitor pick copy of a brief. Priority stays P1. Not a multi-source P0."""
    day = str(item.get("date") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    why = str(item.get("why") or "").strip()
    affect = str(item.get("affect") or "").strip()
    url = safe_http_url(item.get("url") or "")
    if not url or not all(visitor_ready(part) for part in (title, summary, why, affect, _BRIEF_FILL_FALSIFIER)):
        return None
    lens = item.get("lens") if item.get("lens") in LENSES else "赛道"
    copy = item.get("card_copy") if isinstance(item.get("card_copy"), dict) else {}
    evidence = str(copy.get("evidence_label") or "").strip()
    if evidence == "尚待核实":
        status, role = "rumor", "report"
    elif evidence == "多源确认":
        status, role = "confirmed", "analysis"
    else:
        status, role = "confirmed", "primary"
    handle = str(item.get("source") or "").strip()
    if not handle or any(ch.isspace() or ch in "<>" for ch in handle) or len(handle) > 40:
        handle = "原文"
    eid = str(item.get("id") or "").strip()
    if not eid:
        return None
    card = {
        "schema_version": 2,
        "id": eid,
        "status": status,
        "tag": "简讯",
        "lens": lens,
        "priority": "P1",
        "title": title,
        "summary": summary,
        "date": day,
        "url": url,
        "handle": handle,
        "objective": [summary],
        "sources": [{"url": url, "handle": handle, "role": role}],
        "so_what": {
            "lens": lens,
            "impact": why,
            "action": _action_labels_for_brief(item)[0],
            "window": affect,
            "falsifier": _BRIEF_FILL_FALSIFIER,
        },
    }
    candidate = item.get("candidate_id")
    if isinstance(candidate, str) and candidate.strip():
        card["candidate_id"] = candidate.strip()
    clock = item.get("time")
    if isinstance(clock, str) and clock.strip():
        card["time"] = clock.strip()
    return card


def _tool_fill_candidates(all_items: list[dict]) -> list[tuple[dict, dict]]:
    found: list[tuple[dict, dict]] = []
    seen: set[str] = set()
    for it in all_items:
        if it.get("lens") != "工具" and not it.get("tool_radar"):
            continue
        ring = it.get("tool_radar") or "值得关注"
        if ring not in TOOL_RING_LABEL:
            ring = "值得关注"
        if _tool_record(it, ring) is None or not _visitor_card(it):
            continue
        card = copy.deepcopy(it)
        if not str(card.get("summary") or "").strip():
            objective = card.get("objective") or []
            if objective:
                card["summary"] = str(objective[0])
        eid = str(card.get("id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        found.append(
            (
                card,
                {
                    "from": "tool",
                    "actions": _action_labels_for_tool(it, ring),
                    "has_step": bool(str(it.get("first_step") or "").strip()),
                    "stamp": _visitor_stamp(it),
                },
            )
        )
    return found


def _brief_fill_candidates(rows: list[dict], seen: set[str]) -> list[tuple[dict, dict]]:
    found: list[tuple[dict, dict]] = []
    for item in rows:
        card = _brief_pick(item)
        if card is None or card["id"] in seen:
            continue
        seen.add(card["id"])
        found.append(
            (
                card,
                {
                    "from": "brief",
                    "actions": _action_labels_for_brief(item),
                    "has_step": bool(str(item.get("affect") or "").strip()),
                    "stamp": _visitor_stamp(item),
                },
            )
        )
    return found


def build_picks(all_items: list[dict]) -> dict:
    """Hard picks first. A Shanghai day with none gets one tool or brief.

    The shift already runs this after derive_briefs.py, and the briefs publish
    path runs it again. Empty days therefore fill on the next digest without
    a separate command. Practice gates are not read here.
    """
    hard = select_picks([it for it in all_items if _visitor_card(it)], PER_DAY)
    candidates = _tool_fill_candidates(all_items)
    seen = {str(card.get("id") or "") for card, _meta in candidates}
    candidates.extend(_brief_fill_candidates(_brief_rows(), seen))
    for item in _prior_brief_fills():
        eid = str(item.get("id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        so = item.get("so_what") if isinstance(item.get("so_what"), dict) else {}
        action = str(so.get("action") or "").strip() or "持续观察"
        candidates.append(
            (
                copy.deepcopy(item),
                {
                    "from": "brief",
                    "actions": [action],
                    "has_step": bool(str(so.get("window") or "").strip()),
                    "stamp": _visitor_stamp(item),
                },
            )
        )
    fills = fill_empty_pick_days(hard, candidates)
    chosen = list(hard) + fills
    by_day: dict[str, list[dict]] = {}
    for item in chosen:
        by_day.setdefault(str(item.get("date")), []).append(item)
    days = [{"date": day, "items": by_day[day]} for day in sorted(by_day, reverse=True)]
    return {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
        "per_day": PER_DAY,
        "blocked_urls": sorted(identity_urls(list(all_items) + fills)),
        "blocked_ids": sorted(identity_ids(list(all_items) + fills)),
        "days": days,
    }


def drop_promoted_briefs(picks_doc: dict) -> None:
    """A brief lifted into an empty picks day leaves the brief file.

    derive_briefs.py runs before this script on the shift, so it cannot see
    the fill yet. Dropping the row here is what keeps the same event off
    信息简讯. The pick copy is enough for the next run to fill that day again.
    """
    path = PUBLIC / "briefs.json"
    if not path.is_file():
        return
    data = _load_public_json(path)
    items = [item for item in (data.get("items") or []) if isinstance(item, dict)]
    picks = [
        item
        for day in (picks_doc.get("days") or [])
        if isinstance(day, dict)
        for item in (day.get("items") or [])
        if isinstance(item, dict)
    ]
    kept = without_promoted_briefs(items, picks)
    if [item.get("id") for item in kept] == [item.get("id") for item in items]:
        return
    data["items"] = kept
    data["updated"] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间")
    write_stable(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_today3(picks_doc: dict) -> str:
    chosen = [
        item
        for day in (picks_doc.get("days") or [])
        if isinstance(day, dict)
        for item in (day.get("items") or [])
        if isinstance(item, dict)
    ]
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    if chosen:
        today = max(str(it.get("date") or "") for it in chosen)
    day_items = [it for it in chosen if it.get("date") == today]
    picked = day_items[:3]
    lines = [f"AI Radar · 信息精选（{today}）", ""]
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
    lines.append(f"看板 {SITE}today.html")
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


PRACTICE_NOTE = "能照着做的步骤才会出现在这里。没有写清步骤的分享不会上这一页。"


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
            write_stable(dest,
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
    write_stable(dest,
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
    write_stable(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
  <meta name="theme-color" content="#0F1110" />
  <title>{title} · AI Radar</title>
  <link rel="icon" href="../assets/logo.png" />
  <link rel="stylesheet" href="../assets/radar.css" />
</head>
<body>
  <div class="app">
    <script src="../assets/safe-href.js"></script>
    <script src="../assets/shell.js"></script>
    <div class="content">
      <main id="main" class="wide">
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
    write_stable((PUBLIC / "items.json"),
        json.dumps(items_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    write_stable((PUBLIC / "feed.xml"),
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
        write_stable((FEEDS / f"lens-{slug}.xml"),
            build_rss(
                lens_items,
                f"AI Radar · {label}",
                f"只看{label}。",
                SITE + f"feeds/lens-{slug}.xml",
            ),
            encoding="utf-8",
        )

    radar = build_tools_radar(all_items)
    write_stable((PUBLIC / "tools-radar.json"),
        json.dumps(radar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    picks_doc = build_picks(all_items)
    write_stable((PUBLIC / "picks.json"),
        json.dumps(picks_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    drop_promoted_briefs(picks_doc)
    write_stable((PUBLIC / "today3.txt"), build_today3(picks_doc), encoding="utf-8")
    sync_practice_inbox()
    sync_atlas()
    posts = build_blog()

    print(f"derived: {len(all_items)} archive cards → {len(board)} board items")
    print(f"  items.json, feed.xml, feeds/lens-*.xml, tools-radar.json, today3.txt, archive/index.json")
    print(f"  blog: {len(posts)} posts → blog/index.html, blog/<slug>.html, blog/posts.json")


if __name__ == "__main__":
    main()
