#!/usr/bin/env python3
"""Migrate legacy cards in public/archive to schema_version 2 event model.

- Adds id, status, sources[], lens, schema_version
- Drops bullets (objective kept; feed maps objective→bullets if needed)
- Infers rumor from 传闻 titles; maps tag→lens
- Idempotent: skips cards already at schema_version 2 with id
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import source_timestamp_from_record, stamp_first_report
else:
    from .card_times import source_timestamp_from_record, stamp_first_report

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
TZ = timezone(timedelta(hours=8))

TAG_TO_LENS = {
    "工具": "工具",
    "产品": "工具",
    "模型": "赛道",
    "并购": "赛道",
    "行业": "赛道",
    "发布": "时机",
    "论文": "赛道",
    "评测": "赛道",
    "观点": "模式",
    "案例": "模式",
    "安全": "赛道",
}

# Handles that are typically primary (labs / official)
PRIMARY_HANDLES = {
    "openai", "anthropicai", "googledeepmind", "aiatmeta", "deepseek_ai",
    "alibaba_qwen", "mistralai", "huggingface", "sama", "gdb", "karpathy",
}


def slugify(title: str, max_len: int = 48) -> str:
    s = title.lower().strip()
    # keep ascii letters/digits; map CJK to pinyin-less short hash from chars
    ascii_part = re.sub(r"[^a-z0-9]+", "-", s)
    ascii_part = re.sub(r"-+", "-", ascii_part).strip("-")
    if len(ascii_part) >= 8:
        return ascii_part[:max_len].strip("-")
    # fallback: use hex of normalized title
    norm = unicodedata.normalize("NFKC", title)
    h = abs(hash(norm)) % (10**8)
    base = ascii_part or "card"
    return f"{base}-{h}"[:max_len].strip("-")


def infer_lens(tag: str) -> str:
    return TAG_TO_LENS.get(tag, "赛道")


def infer_status(title: str, handle: str) -> str:
    t = title or ""
    if "传闻" in t or "据传" in t or "外媒称" in t[:20]:
        return "rumor"
    h = (handle or "").lstrip("@").lower()
    if h in PRIMARY_HANDLES:
        return "confirmed"
    # analysis/curation accounts → report unless rumor
    return "confirmed" if "传闻" not in t else "rumor"


def infer_role(handle: str, status: str) -> str:
    h = (handle or "").lstrip("@").lower()
    if h in PRIMARY_HANDLES:
        return "primary"
    if status == "rumor":
        return "report"
    # curators / analysts
    if h in {"dotey", "shao__meng", "dongxi_nlp", "natolambert", "simonw"}:
        return "analysis"
    return "report"


def infer_shift_and_lag(date: str, time_s: str):
    """Hours from the display clock to the next publish slot.

    Slots are stored as Beijing time (Asia/Shanghai), not a US West clock
    (PDT→PST on Nov 1 moves the offset from 15h to 16h):
      08:00 daily            morning  主报
      21:00 Monday–Friday    evening  晚班
    13:30 midday is removed. 05:30 silent shift is deferred and is not a slot.
    Returns (shift, lead_lag_hours) or (None, None).
    This assumed lag is lead_lag_hours. Measured lag is ingested_at − published_at.
    """
    if not date or " " not in (time_s or ""):
        return None, None
    try:
        hh, mi = map(int, time_s.split(" ", 1)[1].split(":"))
        y, m, d = map(int, date.split("-"))
        post = datetime(y, m, d, hh, mi, tzinfo=TZ)
    except Exception:
        return None, None
    slots: list[tuple[datetime, str]] = []
    # Friday after 21:00 still needs the next morning; a weekend gap needs Monday.
    for add in range(0, 4):
        day = post + timedelta(days=add)
        slots.append((day.replace(hour=8, minute=0, second=0, microsecond=0), "morning"))
        if day.weekday() < 5:
            slots.append((day.replace(hour=21, minute=0, second=0, microsecond=0), "evening"))
    nxt, shift = min((slot for slot in slots if slot[0] >= post), key=lambda slot: slot[0])
    lag_h = round((nxt - post).total_seconds() / 3600, 2)
    return shift, lag_h


def fill_shift(out: dict) -> dict:
    """Record assumed first-report lag. Never overwrite a value Alba already set."""
    shift, lag = infer_shift_and_lag(out.get("date") or "", out.get("time") or "")
    if shift and not out.get("shift"):
        out["shift"] = shift
    if lag is not None and out.get("lead_lag_hours") is None:
        out["lead_lag_hours"] = lag
        out["lead_lag_basis"] = "assumed_next_digest"
    return out


def fill_report_times(out: dict, source: dict, *, first_write: bool) -> dict:
    """Stamp ingested_at on first archive write; copy published_at only from a real source clock."""
    return stamp_first_report(
        out,
        first_write=first_write,
        source_time=source_timestamp_from_record(source),
    )


def migrate_item(it: dict) -> dict:
    if it.get("schema_version") == 2 and it.get("id") and it.get("sources"):
        # still drop bullets if present; backfill shift / lead_lag when absent.
        # Already on the board: do not invent ingested_at. published_at is filled
        # only when the record already carries a source clock (created_at / pubDate).
        out = dict(it)
        out.pop("bullets", None)
        return fill_shift(fill_report_times(out, it, first_write=False))

    date = (it.get("date") or "1970-01-01").strip()
    ymd = date.replace("-", "")
    title = it.get("title") or "untitled"
    eid = it.get("id") or f"evt-{ymd}-{slugify(title)}"

    handle = it.get("handle") or "unknown"
    url = it.get("url") or ""
    status = it.get("status") or infer_status(title, handle)
    role = infer_role(handle, status)

    objective = list(it.get("objective") or it.get("bullets") or [])
    if not objective:
        objective = [title]

    sources = it.get("sources")
    if not sources:
        sources = [{"url": url, "handle": handle, "role": role}]

    out = {
        "schema_version": 2,
        "id": eid,
        "status": status,
        "tag": it.get("tag") or "动态",
        "lens": it.get("lens") or infer_lens(it.get("tag") or ""),
        "priority": it.get("priority") or "P1",
        "title": title,
        "date": date,
        "time": it.get("time") or "",
        "handle": handle,
        "url": url,
        "objective": objective,
        "sources": sources,
    }

    # optional legacy judgment (kept for display until so_what adopted)
    if it.get("judgment"):
        out["judgment"] = list(it["judgment"])
        out["judgment_label"] = it.get("judgment_label") or "主观判断"
    elif "judgment" in it:
        out["judgment"] = []

    if it.get("correction"):
        out["correction"] = it["correction"]

    # tool fields passthrough
    for k in ("try_url", "access", "integration", "first_step", "alternatives",
              "tool_radar", "so_what", "lead_lag_hours", "lead_lag_basis", "shift",
              "published_at", "ingested_at"):
        if k in it and it[k] is not None:
            out[k] = it[k]

    # Enrich a few known tool cards for demo radar
    if out["lens"] == "工具" and "REA" in title:
        out.setdefault("try_url", "https://github.com/search?q=REA+MCP")
        out.setdefault("access", "开源")
        out.setdefault("integration", "MCP / Claude Code / Codex / Cursor")
        out.setdefault("first_step", "安装 MCP 后对本地二进制跑一轮只读逆向")
        out.setdefault("alternatives", ["Ghidra 手工", "IDA + 脚本"])
        out.setdefault("tool_radar", "评估")
    if "JiuwenSwarm" in title or "jiuwenswarm" in title.lower():
        out.setdefault("try_url", "https://github.com/openJiuwen-ai/jiuwenswarm")
        out.setdefault("access", "开源 Apache-2.0")
        out.setdefault("integration", "OpenAI 兼容 API / 华为云 MaaS / 本地模型")
        out.setdefault("first_step", "clone 仓库，用兼容 API 跑通 Leader→专家示例")
        out.setdefault("alternatives", ["Claude Code swarm", "CrewAI", "AutoGen"])
        out.setdefault("tool_radar", "试用")
        out["lens"] = "工具"

    # Example so_what only when we can write a falsifier
    if "MiMo-V2.6" in title or "MiMo" in title:
        out["so_what"] = {
            "lens": "赛道",
            "impact": "开源侧把「RL 三维扩展」成本数字公开，影响对标闭源 grader 投入叙事",
            "action": "观察",
            "window": "未来 1–2 个季度",
            "confidence": "中",
            "falsifier": "若后续开源复现无法接近报告基准，或官方撤回/大幅修正 RL 成本口径，则此判断作废",
            "thesis_id": "T-002",
        }
        out["lens"] = "赛道"
    if "Reflection" in title and status == "rumor":
        out["so_what"] = {
            "lens": "赛道",
            "impact": "若属实，英伟达在开源模型股权布局继续加码，影响开源分发与 infra 并购预期",
            "action": "观察",
            "window": "未来 2–6 周",
            "confidence": "低",
            "falsifier": "若官方否认洽谈或无独立一手确认，且 Beam 热度消退后无跟进，则此判断作废",
            "thesis_id": "T-004",
        }
        out["lens"] = "赛道"
    if "JiuwenSwarm" in title:
        out["so_what"] = {
            "lens": "工具",
            "impact": "国内大厂开源模型无关 multi-agent harness，可对比 Claude Code / 开源 swarm 的分发路径",
            "action": "试用",
            "window": "本周内可 clone 试跑",
            "confidence": "中",
            "falsifier": "若仓库无实质更新/示例无法对接 OpenAI 兼容 API，或仅为营销壳，则此判断作废",
            "thesis_id": "T-001",
        }

    # Legacy row is materialized as a v2 card here — that is the first archive write
    # of this object. ingested_at = now. published_at only if the row has a source clock.
    return fill_shift(fill_report_times(out, it, first_write=True))


def migrate_archive_file(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [migrate_item(it) for it in data.get("items", [])]
    data["items"] = items
    data["count"] = len(items)
    data["schema_version"] = 2
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(items)


def check_shift_slots() -> None:
    """Publish slots are Beijing 08:00 daily and 21:00 Mon–Fri. 13:30 is not a slot."""
    cases = {
        ("2026-10-12", "10-12 07:00"): ("morning", 1.0),  # Monday
        ("2026-10-12", "10-12 10:00"): ("evening", 11.0),
        ("2026-10-12", "10-12 21:00"): ("evening", 0.0),
        ("2026-10-16", "10-16 22:00"): ("morning", 10.0),  # Friday → Saturday 08:00
        ("2026-10-17", "10-17 09:00"): ("morning", 23.0),  # Saturday → Sunday 08:00
        ("2026-10-18", "10-18 22:00"): ("morning", 10.0),  # Sunday → Monday 08:00
    }
    for (date, time_s), expect in cases.items():
        got = infer_shift_and_lag(date, time_s)
        if got != expect:
            raise SystemExit(f"FAIL shift {date} {time_s}: {got} != {expect}")
    if infer_shift_and_lag("2026-10-13", "10-13 13:30")[0] == "midday":
        raise SystemExit("FAIL shift: 13:30 must not be a publish slot")
    print("OK shift slots")


def main():
    total = 0
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        n = migrate_archive_file(path)
        print(f"migrated {path.name}: {n} cards")
        total += n
    print(f"done, {total} cards")


if __name__ == "__main__":
    main()
