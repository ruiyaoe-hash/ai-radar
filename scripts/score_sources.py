#!/usr/bin/env python3
"""Compute source scoreboard from the public archive.

Metrics per handle:
  - cards, p0_count, first_report (primary role count),
  - rumor_count, confirmed_after_rumor (approx via correction),
  - actions_taken, only from gitignored owner-actions.local.json when that
    file exists. public/owner-actions.json is a published skeleton and is
    never counted. Do not commit a board produced from a local file.

Output: public/source-scores.json + docs note in stdout.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
LOCAL_ACTIONS = (
    ROOT / "owner-actions.local.json",
    PUBLIC / "owner-actions.local.json",
)
TZ = timezone(timedelta(hours=8))


def load_local_actions() -> list:
    for path in LOCAL_ACTIONS:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in (data.get("actions") or []) if isinstance(row, dict)]
    return []


def main():
    stats = defaultdict(lambda: {
        "cards": 0,
        "p0": 0,
        "primary_role": 0,
        "analysis_role": 0,
        "report_role": 0,
        "rumor": 0,
        "confirmed": 0,
        "multi_source": 0,
        "actions_taken": 0,
        "corrections": 0,
    })
    for path in ARCHIVE.glob("????-??-??.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            for s in it.get("sources") or []:
                h = (s.get("handle") or "").lstrip("@")
                if not h:
                    continue
                st = stats[h]
                st["cards"] += 1
                if it.get("priority") == "P0":
                    st["p0"] += 1
                role = s.get("role") or "report"
                st[f"{role}_role"] = st.get(f"{role}_role", 0) + 1
                st[it.get("status") or "confirmed"] = st.get(it.get("status") or "confirmed", 0) + 1
                if it.get("correction"):
                    st["corrections"] += 1

    local_actions = load_local_actions()
    if local_actions:
        # map event id -> handles via archive index in memory
        id_to_handles = {}
        for path in ARCHIVE.glob("????-??-??.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for it in data.get("items") or []:
                id_to_handles[it["id"]] = [
                    (s.get("handle") or "").lstrip("@") for s in (it.get("sources") or [])
                ]
        for row in local_actions:
            if row.get("action") in {"tried", "thesis_updated", "shared"}:
                for h in id_to_handles.get(row.get("event_id"), []):
                    if h:
                        stats[h]["actions_taken"] += 1
        print("note: owner-actions.local.json affected actions_taken; do not commit this board")

    board = []
    for h, st in stats.items():
        # simple score: actions*5 + p0*2 + primary*3 - rumor*1 - corrections*3
        score = (
            st["actions_taken"] * 5
            + st["p0"] * 2
            + st["primary_role"] * 3
            + st["analysis_role"]
            - st["rumor"]
            - st["corrections"] * 3
        )
        board.append({"handle": h, "score": score, **st})
    board.sort(key=lambda x: (-x["score"], -x["cards"], x["handle"]))

    out = {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
        "formula": "actions*5 + p0*2 + primary*3 + analysis - rumor - corrections*3",
        "sources": board,
    }
    (PUBLIC / "source-scores.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote public/source-scores.json ({len(board)} handles)")


if __name__ == "__main__":
    main()
