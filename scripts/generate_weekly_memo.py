#!/usr/bin/env python3
"""Draft a weekly decision memo from public/archive (human edits after).

Spoken blocks follow docs/AIHOT对接与表达规范-v0.md via scripts/human_layer.py.
Card ids stay in the appendix. Priority rules are unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import measured_lag_hours
    from human_layer import digest_card_md
else:
    from .card_times import measured_lag_hours
    from .human_layer import digest_card_md

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
OUT_DIR = PUBLIC / "memos"
TZ = timezone(timedelta(hours=8))


def load_range(start: str, end: str) -> list[dict]:
    items = []
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        if path.stem < start or path.stem > end:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items.extend(data.get("items") or [])
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--end", default=None, help="YYYY-MM-DD inclusive (default today CST)")
    args = ap.parse_args()
    end = args.end or datetime.now(TZ).strftime("%Y-%m-%d")
    y, m, d = map(int, end.split("-"))
    start = (datetime(y, m, d, tzinfo=TZ) - timedelta(days=args.days - 1)).strftime("%Y-%m-%d")

    items = load_range(start, end)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"weekly-{end}.md"

    by_lens = Counter(it.get("lens") for it in items)
    p0 = [it for it in items if it.get("priority") == "P0"]
    p0_pending = [it for it in p0 if it.get("status") == "rumor"]
    p0_formal = [it for it in p0 if it.get("status") != "rumor"]
    with_so = [it for it in items if it.get("so_what")]
    tools = [it for it in items if it.get("lens") == "工具"]

    lines = [
        f"# AI Radar 周度决策备忘草稿（{start} → {end}）",
        "",
        "> 自动起草 · 请人工改定后再分发。成功指标默认：每周 ≥3 个工具/赛道决策（可调）。",
        "",
        "## 1. 本周信号概览",
        f"- 卡片总数：{len(items)}",
        f"- 重磅：{len(p0_formal)}；尚待核实：{len(p0_pending)}",
        f"- 按 lens：{dict(by_lens)}",
        f"- 含 so_what（可证伪）：{len(with_so)}",
        "",
        "## 2. 本周重磅",
        "",
        "> 这里只收已经核对、值得单独看的重点。内部编号在文末附录。",
        "",
    ]
    if not p0_formal:
        lines.append("- （无）")
    for it in p0_formal:
        lines.append(digest_card_md(it).rstrip())
        lines.append("")
        lines.append("- 建议主人记下：tried / thesis_updated / shared / ignored")
        lines.append("")
    lines += ["", "## 3. 传闻，先核对", ""]
    if not p0_pending:
        lines.append("- （无）")
    for it in p0_pending:
        lines.append(f"- {it.get('title')} — 还缺一手，或还缺两个独立来源。先不要当成重磅。")

    lines += ["", "## 4. 工具雷达候选"]
    if not tools:
        lines.append("- （无）")
    for it in tools:
        raw_ring = str(it.get("tool_radar") or "")
        ring = {
            "采纳": "推荐使用",
            "试用": "推荐使用",
            "评估": "值得关注",
            "暂缓": "值得关注",
            "推荐使用": "推荐使用",
            "值得关注": "值得关注",
        }.get(raw_ring, "值得关注")
        lines.append(f"- [{ring}] {it.get('title')} — {it.get('try_url') or it.get('url')}")

    measured = [lag for it in items if (lag := measured_lag_hours(it)) is not None]
    if measured:
        mid = sorted(measured)[len(measured) // 2]
        lag_line = f"- 本窗口可测 {len(measured)} 张；中位 {mid} 小时。"
    else:
        lag_line = "- 本窗口还没有同时带 `published_at` 与 `ingested_at` 的卡。"

    lines += [
        "",
        "## 5. 论点（theses）挂钩",
        "- 打开 `public/theses.json`，把本周支持/反对证据挂到对应 thesis_id。",
        "",
        "## 6. 噪声观察",
        "- 连续两周无主人 action 的信源/标签/P0 类型 → 降权或移出 A 级。",
        "",
        "## 7. 班次与首报时差",
        "- 班次（北京时间 Asia/Shanghai，不写成美西钟点；11 月 1 日 PDT→PST，时差 15h→16h）：每天 08:00 主报；周一至周五 21:00 晚班短报。13:30 午间已取消。05:30 静默班延至飞书出站 webhook 可用。",
        "- 假定下一班时差仍记 `lead_lag_hours`（`lead_lag_basis=assumed_next_digest`），已有值不覆盖。",
        "- 实测首报时差 = `ingested_at` − `published_at`（两枚都在才算）。旧卡可以没有这两枚时间。",
        lag_line,
        "",
        "## 附录 · 机器编号（不进主报正文）",
        "",
    ]
    for it in p0_formal + p0_pending:
        eid = it.get("id")
        if eid:
            lines.append(f"- `{eid}`")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
