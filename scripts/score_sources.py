#!/usr/bin/env python3
"""Compute source scoreboard from the public archive.

Metrics per handle:
  - cards, p0_count, first_report (primary role count),
  - rumor_count, confirmed_after_rumor (approx via correction),
  - actions_taken, only from gitignored owner-actions.local.json when that
    file exists. public/owner-actions.json is a published skeleton and is
    never counted. Do not commit a board produced from a local file.
  - dropped: pool rows with status dropped, one count per candidate id.
    Pass --pool-dir to include them. Without it the board is archive-only
    and pool_drops_included is false (survivor bias remains).
  - bookmark_like_ratio: (bookmarks + 3) / (likes + 5) over engagement on
    those pool rows, including discarded posts. Null when no counts exist.

The integer `score` formula is unchanged. Hit rate and bookmark/like are
separate fields so a private pool is not required to refresh the public board.

Output: public/source-scores.json
Do not commit a run that used --pool-dir or owner-actions.local.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from score_pool import smoothed_bookmark_like, smoothed_hit_rate
else:
    from .score_pool import smoothed_bookmark_like, smoothed_hit_rate

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
LOCAL_ACTIONS = (
    ROOT / "owner-actions.local.json",
    PUBLIC / "owner-actions.local.json",
)
TZ = timezone(timedelta(hours=8))
FORMULA = (
    "score = actions*5 + p0*2 + primary*3 + analysis - rumor - corrections*3; "
    "hit_rate = (cards+2)/(cards+dropped+4); "
    "bookmark_like_ratio = (bookmarks+3)/(likes+5) when engagement rows are passed, "
    "including discarded posts"
)


def load_local_actions() -> list:
    for path in LOCAL_ACTIONS:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in (data.get("actions") or []) if isinstance(row, dict)]
    return []


def _blank() -> dict:
    return {
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
        "dropped": 0,
        "bookmark_sum": 0,
        "like_sum": 0,
        "engagement_samples": 0,
    }


def empty_stats():
    return defaultdict(_blank)


def apply_archive(stats, archive: Path) -> dict:
    id_to_handles = {}
    for path in sorted(archive.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            handles = []
            for source in it.get("sources") or []:
                handle = (source.get("handle") or "").lstrip("@")
                if not handle:
                    continue
                handles.append(handle)
                st = stats[handle]
                st["cards"] += 1
                if it.get("priority") == "P0":
                    st["p0"] += 1
                role = source.get("role") or "report"
                st[f"{role}_role"] = st.get(f"{role}_role", 0) + 1
                st[it.get("status") or "confirmed"] = st.get(it.get("status") or "confirmed", 0) + 1
                if it.get("correction"):
                    st["corrections"] += 1
            if it.get("id"):
                id_to_handles[it["id"]] = handles
    return id_to_handles


def apply_actions(stats, id_to_handles: dict, actions: list) -> bool:
    used = False
    for row in actions:
        if row.get("action") in {"tried", "thesis_updated", "shared"}:
            used = True
            for handle in id_to_handles.get(row.get("event_id"), []):
                if handle:
                    stats[handle]["actions_taken"] += 1
    return used


def iter_pool_rows(pool_dir: Path) -> list[dict]:
    rows = []
    folder = pool_dir / "candidates"
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def apply_pool_rows(stats, rows: list[dict]) -> None:
    """Count each candidate id once. Promoted ids are not also drops. Engagement includes drops."""
    promoted: dict[str, set] = defaultdict(set)
    seen_drop: dict[str, set] = defaultdict(set)
    for row in rows:
        handle = ((row.get("source") or {}).get("handle") or "").lstrip("@").strip()
        if not handle or row.get("status_in_pool") != "promoted":
            continue
        promoted[handle].add(row.get("id"))
    for row in rows:
        handle = ((row.get("source") or {}).get("handle") or "").lstrip("@").strip()
        if not handle:
            continue
        rid = row.get("id")
        if row.get("status_in_pool") == "dropped" and rid not in promoted[handle] and rid not in seen_drop[handle]:
            seen_drop[handle].add(rid)
            stats[handle]["dropped"] += 1
        engagement = row.get("engagement") if isinstance(row.get("engagement"), dict) else None
        if not engagement:
            continue
        if "bookmarks" not in engagement and "likes" not in engagement:
            continue
        stats[handle]["bookmark_sum"] += int(engagement.get("bookmarks") or 0)
        stats[handle]["like_sum"] += int(engagement.get("likes") or 0)
        stats[handle]["engagement_samples"] += 1


def row_score(st: dict) -> int:
    return (
        st["actions_taken"] * 5
        + st["p0"] * 2
        + st["primary_role"] * 3
        + st["analysis_role"]
        - st["rumor"]
        - st["corrections"] * 3
    )


def board_from_stats(stats, pool_drops_included: bool) -> list[dict]:
    board = []
    for handle, st in stats.items():
        samples = st["engagement_samples"]
        ratio = None
        if samples:
            ratio = round(smoothed_bookmark_like(st["bookmark_sum"], st["like_sum"]), 4)
        public = {key: value for key, value in st.items() if key not in {"bookmark_sum", "like_sum", "engagement_samples"}}
        board.append(
            {
                "handle": handle,
                "score": row_score(st),
                **public,
                "hit_rate": round(smoothed_hit_rate(st["cards"], st["dropped"]), 4),
                "bookmark_like_ratio": ratio,
                "bookmark_like_samples": samples,
                "pool_drops_included": pool_drops_included,
            }
        )
    board.sort(key=lambda item: (-item["score"], -item["cards"], item["handle"]))
    return board


def build_board(archive: Path, pool_rows: list[dict] | None, actions: list | None = None) -> tuple[list[dict], bool]:
    stats = empty_stats()
    id_to_handles = apply_archive(stats, archive)
    local = apply_actions(stats, id_to_handles, actions or [])
    if pool_rows is not None:
        apply_pool_rows(stats, pool_rows)
    return board_from_stats(stats, pool_rows is not None), local


def self_check() -> None:
    """Synthetic rows. Does not rewrite public/source-scores.json."""
    kept = smoothed_hit_rate(1, 0)
    with_drops = smoothed_hit_rate(1, 4)
    if not with_drops < kept:
        raise SystemExit("FAIL: discarded posts must lower hit_rate")
    raw = 30 / 10
    smooth = smoothed_bookmark_like(30, 10)
    if not 0 < smooth < raw:
        raise SystemExit(f"FAIL: bookmark/like smooth {smooth} vs raw {raw}")
    stats = empty_stats()
    stats["fixturelab"]["cards"] = 1
    stats["fixturelab"]["analysis_role"] = 1
    stats["fixturelab"]["confirmed"] = 1
    clean = board_from_stats(stats, False)[0]["hit_rate"]
    stats["fixturelab"]["dropped"] = 4
    dirty = board_from_stats(stats, True)[0]["hit_rate"]
    if not dirty < clean:
        raise SystemExit(f"FAIL: pool drops did not move hit_rate {dirty} vs {clean}")

    rows = [
        {
            "id": "cand-20261014-ddddddddddd1",
            "status_in_pool": "dropped",
            "drop_reason": "low_score",
            "source": {"handle": "fixturelab"},
            "engagement": {"likes": 10, "bookmarks": 1},
        },
        {
            "id": "cand-20261014-ddddddddddd1",
            "status_in_pool": "dropped",
            "drop_reason": "duplicate_url",
            "source": {"handle": "fixturelab"},
            "engagement": {"likes": 10, "bookmarks": 1},
        },
        {
            "id": "cand-20261014-ddddddddddd2",
            "status_in_pool": "promoted",
            "source": {"handle": "fixturelab"},
            "engagement": {"likes": 10, "bookmarks": 40},
        },
        {
            "id": "cand-20261014-ddddddddddd3",
            "status_in_pool": "active",
            "source": {"handle": "quietlab"},
            "engagement": {"likes": 10, "bookmarks": 0},
        },
    ]
    measured = empty_stats()
    apply_pool_rows(measured, rows)
    if measured["fixturelab"]["dropped"] != 1:
        raise SystemExit(f"FAIL: duplicate drop id counted {measured['fixturelab']['dropped']} times")
    if measured["fixturelab"]["engagement_samples"] != 3:
        raise SystemExit(
            f"FAIL: engagement samples {measured['fixturelab']['engagement_samples']}; "
            "discarded rows must be included and a duplicate id still counts its own row"
        )
    if measured["fixturelab"]["bookmark_sum"] != 42:
        raise SystemExit(f"FAIL: bookmark sum {measured['fixturelab']['bookmark_sum']}")
    promoted_ratio = smoothed_bookmark_like(40, 10)
    with_drop_ratio = smoothed_bookmark_like(42, 30)
    if with_drop_ratio == promoted_ratio:
        raise SystemExit("FAIL: a discarded post did not change bookmark/like")
    board = board_from_stats(measured, True)
    by_handle = {item["handle"]: item for item in board}
    if by_handle["fixturelab"]["bookmark_like_ratio"] != round(with_drop_ratio, 4):
        raise SystemExit("FAIL: board ratio drifted from the smoothed function")
    if by_handle["quietlab"]["pool_drops_included"] is not True:
        raise SystemExit("FAIL: pool flag missing")
    print("OK score_sources self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write public/source-scores.json from the archive.")
    parser.add_argument("--pool-dir", help="Optional private pool. Do not commit the board this produces.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    pool_rows = None
    if args.pool_dir:
        pool_rows = iter_pool_rows(Path(args.pool_dir))
        print("note: --pool-dir affected dropped and bookmark_like; do not commit this board")
    actions = load_local_actions()
    board, used_actions = build_board(ARCHIVE, pool_rows, actions)
    if used_actions:
        print("note: owner-actions.local.json affected actions_taken; do not commit this board")
    out = {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M 北京时间"),
        "formula": FORMULA,
        "pool_drops_included": pool_rows is not None,
        "sources": board,
    }
    (PUBLIC / "source-scores.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote public/source-scores.json ({len(board)} handles)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
