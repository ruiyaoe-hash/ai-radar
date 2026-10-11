#!/usr/bin/env python3
"""Draft a weekly decision memo from public/archive (human edits after)."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        f"- 正式 P0：{len(p0_formal)}；P0-待证（rumor）：{len(p0_pending)}",
        f"- 按 lens：{dict(by_lens)}",
        f"- 含 so_what（可证伪）：{len(with_so)}",
        "",
        "## 2. 正式 P0（需决策）",
    ]
    if not p0_formal:
        lines.append("- （无）")
    for it in p0_formal:
        lines.append(f"- **{it.get('title')}** `{it.get('id')}` · {it.get('lens')} · {it.get('status')}")
        if it.get("so_what"):
            so = it["so_what"]
            lines.append(f"  - impact: {so.get('impact')}")
            lines.append(f"  - action: {so.get('action')} · falsifier: {so.get('falsifier')}")
        lines.append(f"  - 建议主人 action：tried / thesis_updated / shared / ignored")
    lines += ["", "## 3. P0-待证（勿当正式信号）"]
    if not p0_pending:
        lines.append("- （无）")
    for it in p0_pending:
        lines.append(f"- {it.get('title')} `{it.get('id')}` — 待一手或两独立源确认")

    lines += ["", "## 4. 工具雷达候选"]
    if not tools:
        lines.append("- （无）")
    for it in tools:
        ring = it.get("tool_radar") or "（未分环）"
        lines.append(f"- [{ring}] {it.get('title')} — {it.get('try_url') or it.get('url')}")

    lines += [
        "",
        "## 5. 论点（theses）挂钩",
        "- 打开 `public/theses.json`，把本周支持/反对证据挂到对应 thesis_id。",
        "",
        "## 6. 噪声观察",
        "- 连续两周无主人 action 的信源/标签/P0 类型 → 降权或移出 A 级。",
        "",
        "## 7. 下周验证班次",
        "- 假设：13:30 主报 → 20:00–21:00 晚间复核；记录 `lead_lag_hours`。",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
