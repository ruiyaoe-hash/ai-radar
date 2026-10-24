#!/usr/bin/env python3
"""Which public door an archive card belongs to.

信息精选 is the top few cards per Shanghai calendar day that already passed
selection: priority P0, a multi-source card, or two different source handles
on the same card. 信息简讯 never receives those URLs. This module only reads
public archive cards. It does not read the private pool.

  python3 scripts/lanes.py --self-check
"""
from __future__ import annotations

import re
from datetime import datetime

PER_DAY = 3
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _handles(item: dict) -> set[str]:
    found: set[str] = set()
    for source in item.get("sources") or []:
        if isinstance(source, dict) and source.get("handle"):
            found.add(str(source["handle"]).strip().lower())
    handle = item.get("handle")
    if isinstance(handle, str) and handle.strip():
        found.add(handle.strip().lower())
    return found


def qualifies_pick(item: dict) -> bool:
    """True when the card is a 信息精选 item, not a news brief."""
    if not isinstance(item, dict):
        return False
    if item.get("priority") == "P0":
        return True
    if item.get("status") == "multi_source":
        return True
    if len(_handles(item)) >= 2:
        return True
    return False


def _stamp(item: dict) -> float:
    raw = item.get("published_at") or item.get("ingested_at") or ""
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return 0.0


def rank_key(item: dict) -> tuple:
    """Most important first. Stable for a fixed archive."""
    priority = 0 if item.get("priority") == "P0" else 1
    multi = 0 if item.get("status") == "multi_source" or len(_handles(item)) >= 2 else 1
    confirmed = 0 if item.get("status") == "confirmed" else 1
    return (priority, multi, confirmed, -_stamp(item), str(item.get("id") or ""))


def select_picks(items: list[dict], per_day: int = PER_DAY) -> list[dict]:
    """Up to per_day qualifying cards for every day. Newest day is not special."""
    by_day: dict[str, list[dict]] = {}
    for item in items:
        if not qualifies_pick(item):
            continue
        day = str(item.get("date") or "")
        if not _DAY.match(day):
            continue
        by_day.setdefault(day, []).append(item)
    chosen: list[dict] = []
    for day in sorted(by_day):
        ranked = sorted(by_day[day], key=rank_key)
        chosen.extend(ranked[:per_day])
    return chosen


def identity_urls(items: list[dict]) -> set[str]:
    found: set[str] = set()
    for item in items:
        raw_values = [item.get("url"), item.get("try_url")]
        for source in item.get("sources") or []:
            if isinstance(source, dict):
                raw_values.append(source.get("url"))
        for raw in raw_values:
            if isinstance(raw, str) and raw.strip():
                found.add(raw.strip())
    return found


def identity_ids(items: list[dict]) -> set[str]:
    found: set[str] = set()
    for item in items:
        for key in ("id", "candidate_id"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                found.add(value.strip())
    return found


def self_check() -> None:
    day = "2026-10-24"
    cards = []
    for index, priority in enumerate(("P0", "P0", "P0", "P1", "P2")):
        cards.append(
            {
                "id": f"evt-20261024-card{index}",
                "priority": priority,
                "status": "confirmed",
                "date": day,
                "title": f"标题{index}",
                "url": f"https://example.com/{index}",
                "published_at": f"2026-10-24T0{index}:00:00Z",
                "sources": [{"url": f"https://example.com/{index}", "handle": "lab"}],
            }
        )
    cards.append(
        {
            "id": "evt-20261023-multi",
            "priority": "P1",
            "status": "multi_source",
            "date": "2026-10-23",
            "title": "同一件事",
            "url": "https://example.com/multi",
            "published_at": "2026-10-23T01:00:00Z",
            "sources": [
                {"url": "https://example.com/multi", "handle": "one"},
                {"url": "https://example.com/multi-b", "handle": "two"},
            ],
        }
    )
    plain = {
        "id": "evt-20261023-plain",
        "priority": "P1",
        "status": "confirmed",
        "date": "2026-10-23",
        "title": "单源普通",
        "url": "https://example.com/plain",
        "sources": [{"url": "https://example.com/plain", "handle": "solo"}],
    }
    picked = select_picks(cards + [plain])
    ids = [item["id"] for item in picked]
    if ids.count("evt-20261024-card0") != 1 or "evt-20261024-card3" in ids or "evt-20261024-card4" in ids:
        raise SystemExit(f"FAIL: daily cap {ids}")
    if sum(1 for item in picked if item["date"] == day) != 3:
        raise SystemExit("FAIL: a day must keep three picks when more qualify")
    if "evt-20261023-multi" not in ids or "evt-20261023-plain" in ids:
        raise SystemExit(f"FAIL: multi-source boundary {ids}")
    if "https://example.com/multi-b" not in identity_urls(picked):
        raise SystemExit("FAIL: source urls missing from the pick identity set")
    print("OK lanes self-check")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pick selection for the public doors.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    parser.error("pass --self-check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
