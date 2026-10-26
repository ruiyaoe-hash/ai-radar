#!/usr/bin/env python3
"""Which public door an archive card belongs to.

信息精选 is the top few cards per Shanghai calendar day that already passed
selection: priority P0, a multi-source card, or two different source handles
on the same card. That gate is not lowered to fill a day.

When a Shanghai day still has zero picks, one same-day tool or brief can
stand in (see fill_empty_pick_days). The stand-in is not marked P0, and a
second card is not added. 信息简讯 does not keep a brief that was promoted
into that empty day. This module only reads public cards. It does not read
the private pool.

  python3 scripts/lanes.py --self-check
"""
from __future__ import annotations

import copy
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
    """Up to per_day qualifying cards for every day. Newest day is not special.

    Days with no qualifier stay empty here. Empty-day fill is a separate step
    and does not call this with a weaker gate.
    """
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


def _norm_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/").lower()


# Empty-day ranking for one stand-in. Clearer mass-visitor action first.
# This does not relax P0 / multi-source, and it does not add a second card.
#   立即行动 / 值得采用  >  可以试用  >  持续观察  >  需要评估  >  暂缓
# Same band: a concrete next step (上手实验, or 对我有什么影响) ranks ahead.
# Still tied: newer source clock, then id.
# A tool does not outrank a brief unless its action band is clearer.
_ACTION_RANK = {
    "立即行动": 0,
    "值得采用": 0,
    "可以试用": 1,
    "持续观察": 2,
    "需要评估": 3,
    "暂缓跟进": 4,
    "暂缓": 4,
}


def action_rank(labels) -> int:
    """Lower is a clearer mass-visitor action. Unknown labels sort last."""
    ranks = []
    for label in labels or []:
        text = str(label or "").strip()
        if text in _ACTION_RANK:
            ranks.append(_ACTION_RANK[text])
    return min(ranks) if ranks else 5


def fill_empty_pick_days(hard_picks: list[dict], candidates: list[tuple[dict, dict]]) -> list[dict]:
    """One stand-in for each Shanghai day that has zero hard picks.

    candidates are (card, meta). meta keys: from ("tool"|"brief"), actions
    (labels in _ACTION_RANK), has_step (bool), stamp (float). Cards that
    already qualify_pick are ignored so this path cannot mint a P0.
    The returned cards are copies with fill_reason / promoted_from set.
    """
    occupied = {
        str(item.get("date") or "")
        for item in hard_picks
        if _DAY.match(str(item.get("date") or ""))
    }
    seen: set[str] = set()
    by_day: dict[str, list[tuple]] = {}
    for card, meta in candidates:
        if not isinstance(card, dict) or not isinstance(meta, dict):
            continue
        if meta.get("from") not in {"tool", "brief"}:
            continue
        if qualifies_pick(card):
            continue
        day = str(card.get("date") or "")
        if not _DAY.match(day) or day in occupied:
            continue
        eid = str(card.get("id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        key = (
            action_rank(meta.get("actions") or []),
            0 if meta.get("has_step") else 1,
            -float(meta.get("stamp") or 0),
            eid,
        )
        by_day.setdefault(day, []).append((key, card, meta))
    chosen: list[dict] = []
    for day in sorted(by_day):
        _key, card, meta = sorted(by_day[day], key=lambda part: part[0])[0]
        pick = copy.deepcopy(card)
        pick["fill_reason"] = "empty_day"
        pick["promoted_from"] = meta["from"]
        chosen.append(pick)
    return chosen


def without_promoted_briefs(briefs: list[dict], picks: list[dict]) -> list[dict]:
    """Drop briefs that are the same event as an empty-day fill.

    Home and 信息简讯 already hide pick URLs. Removing the row keeps the
    brief file from carrying a second copy after the fill is written.
    """
    fills = [
        item
        for item in picks
        if isinstance(item, dict) and item.get("fill_reason") == "empty_day"
    ]
    ids: set[str] = set()
    urls: set[str] = set()
    for item in fills:
        ids |= identity_ids([item])
        urls |= {_norm_url(url) for url in identity_urls([item])}
        urls.discard("")
    if not ids and not urls:
        return [item for item in briefs if isinstance(item, dict)]
    kept: list[dict] = []
    for item in briefs:
        if not isinstance(item, dict):
            continue
        item_ids = identity_ids([item])
        item_urls = {_norm_url(item.get("url"))}
        item_urls |= {_norm_url(url) for url in identity_urls([item])}
        item_urls.discard("")
        if item_ids & ids or item_urls & urls:
            continue
        kept.append(item)
    return kept


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
    if not (action_rank(["可以试用"]) < action_rank(["持续观察"]) < action_rank(["暂缓"])):
        raise SystemExit("FAIL: mass-visitor action bands")
    if action_rank(["暂缓", "立即行动"]) != 0 or action_rank([]) != 5:
        raise SystemExit("FAIL: action rank should keep the clearer label")

    def fill_card(eid: str, day: str, priority: str = "P1") -> dict:
        return {
            "id": eid,
            "priority": priority,
            "status": "confirmed",
            "date": day,
            "title": "访客能读的一条标题",
            "summary": "这是写给访客的摘要，说明今天可以做什么。",
            "objective": ["这是写给访客的摘要，说明今天可以做什么。"],
            "so_what": {
                "impact": "如果你这周要做这件事，这条会改变下一步。",
                "action": "持续观察",
                "window": "对不上就保持原来的做法。",
                "falsifier": "如果原文被撤回，就不必改这周的安排。",
            },
            "url": f"https://example.com/{eid}",
            "sources": [{"url": f"https://example.com/{eid}", "handle": "lab", "role": "primary"}],
        }

    strong = fill_card("evt-20261026-tool", "2026-10-26")
    weak = fill_card("brf-20261026-weak", "2026-10-26")
    filled = fill_empty_pick_days(
        [],
        [
            (weak, {"from": "brief", "actions": ["持续观察"], "has_step": True, "stamp": 50}),
            (strong, {"from": "tool", "actions": ["立即行动", "可以试用"], "has_step": True, "stamp": 1}),
        ],
    )
    if len(filled) != 1 or filled[0]["id"] != "evt-20261026-tool":
        raise SystemExit(f"FAIL: empty day must keep the clearer action, not the newer brief {filled}")
    if filled[0]["priority"] != "P1" or filled[0].get("status") == "multi_source":
        raise SystemExit("FAIL: empty-day fill must not become a hard P0")
    if qualifies_pick(filled[0]):
        raise SystemExit("FAIL: fill path published a card that already clears the hard gate")
    if filled[0].get("fill_reason") != "empty_day" or filled[0].get("promoted_from") != "tool":
        raise SystemExit("FAIL: fill provenance missing")
    if "fill_reason" in strong or "promoted_from" in strong:
        raise SystemExit("FAIL: fill mutated the source card")
    prose = " ".join(
        [
            str(filled[0].get("title") or ""),
            str(filled[0].get("summary") or ""),
            " ".join(str(line) for line in filled[0].get("objective") or []),
            " ".join(str(value) for value in (filled[0].get("so_what") or {}).values()),
        ]
    )
    for token in ("fill_reason", "promoted_from", "empty_day", "P0"):
        if token in prose:
            raise SystemExit(f"FAIL: visitor copy contains {token}")

    hard = fill_card("evt-20261026-hard", "2026-10-26", "P0")
    if fill_empty_pick_days([hard], [(strong, {"from": "tool", "actions": ["立即行动"], "has_step": True, "stamp": 9})]):
        raise SystemExit("FAIL: a day that already has a pick gained a second card")
    laundered = fill_empty_pick_days(
        [],
        [
            (hard, {"from": "tool", "actions": ["立即行动"], "has_step": True, "stamp": 9}),
            (weak, {"from": "brief", "actions": ["持续观察"], "has_step": True, "stamp": 1}),
        ],
    )
    if [item["id"] for item in laundered] != ["brf-20261026-weak"]:
        raise SystemExit(f"FAIL: a qualifying card was relabeled as a fill {laundered}")

    stepped = fill_card("evt-20261025-step", "2026-10-25")
    bare = fill_card("evt-20261025-bare", "2026-10-25")
    stepped_fill = fill_empty_pick_days(
        [],
        [
            (bare, {"from": "tool", "actions": ["可以试用"], "has_step": False, "stamp": 20}),
            (stepped, {"from": "brief", "actions": ["可以试用"], "has_step": True, "stamp": 1}),
        ],
    )
    if [item["id"] for item in stepped_fill] != ["evt-20261025-step"]:
        raise SystemExit("FAIL: same action band should prefer the concrete next step")
    if stepped_fill[0]["promoted_from"] != "brief":
        raise SystemExit("FAIL: a brief with a clearer step lost to a tool on a tie")

    defer_tool = fill_card("evt-20261027-defer", "2026-10-27")
    urgent = fill_card("brf-20261027-act", "2026-10-27")
    urgent_fill = fill_empty_pick_days(
        [],
        [
            (defer_tool, {"from": "tool", "actions": ["暂缓"], "has_step": True, "stamp": 30}),
            (urgent, {"from": "brief", "actions": ["立即行动"], "has_step": True, "stamp": 2}),
        ],
    )
    if len(urgent_fill) != 1 or urgent_fill[0]["promoted_from"] != "brief":
        raise SystemExit("FAIL: a defer tool outranked an immediate brief")

    other = fill_card("brf-20261026-keep", "2026-10-26")
    other["url"] = "https://example.com/keep"
    same_event = fill_card("brf-20261026-same", "2026-10-26")
    same_event["url"] = "https://example.com/evt-20261026-tool/"
    kept = without_promoted_briefs([same_event, other, weak], filled)
    kept_ids = [item["id"] for item in kept]
    if kept_ids != ["brf-20261026-keep", "brf-20261026-weak"]:
        raise SystemExit(f"FAIL: promoted event still in briefs {kept_ids}")
    promoted_brief = fill_card("brf-20261027-act", "2026-10-27")
    promoted_brief["fill_reason"] = "empty_day"
    promoted_brief["promoted_from"] = "brief"
    promoted_brief["candidate_id"] = "cand-20261027-act"
    twin = fill_card("brf-other", "2026-10-27")
    twin["candidate_id"] = "cand-20261027-act"
    twin["url"] = "https://example.com/different"
    if without_promoted_briefs([promoted_brief, twin, other], [promoted_brief]) != [other]:
        raise SystemExit("FAIL: brief promoted by id still remains in the brief list")
    if without_promoted_briefs([other], []) != [other]:
        raise SystemExit("FAIL: briefs dropped when nothing was promoted")
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
