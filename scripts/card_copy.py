#!/usr/bin/env python3
"""Card copy for a scored row. Words for a card, not the algorithm numbers.

The public site uses five visitor doors: 信息精选, 信息简讯, 工具决策, 实战手册, 专题观察.
This module only fills the copy those cards can show. It does not render HTML.

  python3 scripts/card_copy.py --self-check

watch_reason is a fixed Chinese sentence. It never copies the post, and it
never includes a digit, so a score or a version cannot leak into the label.
high_priority_review means Forced P0 is waiting for a person. It is not a
publish flag and it is not the archive card's priority field (P0 / P1).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from force_p0 import TOOL_CHOICE_RE, row_text
    from ingest_x import IngestError
else:
    from .force_p0 import TOOL_CHOICE_RE, row_text
    from .ingest_x import IngestError

EVIDENCE_LABELS = ("官方原始信息", "多源确认", "尚待核实")
SUGGESTED_ACTIONS = ("立即行动", "持续观察", "暂缓")

OFFICIAL_REASON = "官方源发布了新说明。"
MULTI_REASON = "不止一个独立来源提到这件事，仍等人核对。"
HELD_REASON = "时间上赶不上今日这一档，先记下，不是因为价值低。"
DROP_REASON = "这一条先不进公开页。"
WATCH_REASON = "先看着，等更多能核对的来源。"
VULN_REASON = "运行时漏洞已给出可升级版本，值得优先核对。"
FRONTIER_REASON = "前沿实验室放出了新产品线或研究预览，值得先盯着。"
TOOL_REASON = "同一天有多位高可信账号在说同一件事，而且可能改变这周的工具选择。"
QUEUE_REASON = "同一天有多位高可信账号在说同一件事，先看一眼再决定。"

_DIGIT = re.compile(r"[0-9]")
_LEAK = re.compile(r"value\s*=|score|confidence|snippet|band_reason", re.I)


def public_auto_copy() -> dict:
    """Editor-side flash wording. Public briefs do not attach this object."""
    return {
        "watch_reason": OFFICIAL_REASON,
        "evidence_label": "官方原始信息",
        "suggested_action": "持续观察",
        "high_priority_review": False,
    }


def refuses_auto_publish(row: dict) -> bool:
    """Forced P0 stays in the human queue. Never project it as an auto brief."""
    spec = row.get("force_p0") if isinstance(row.get("force_p0"), dict) else {}
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    copy = row.get("card_copy") if isinstance(row.get("card_copy"), dict) else {}
    if spec.get("active"):
        return True
    if score.get("band_reason") == "review_p0":
        return True
    if copy.get("high_priority_review") is True:
        return True
    return False


def _check(copy: dict) -> dict:
    reason = copy.get("watch_reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 80:
        raise IngestError("card_copy.watch_reason must be a short sentence")
    if _DIGIT.search(reason) or _LEAK.search(reason):
        raise IngestError("card_copy.watch_reason must not carry a score, a version, or the post")
    if copy.get("evidence_label") not in EVIDENCE_LABELS:
        raise IngestError("card_copy.evidence_label is not one of the three labels")
    if copy.get("suggested_action") not in SUGGESTED_ACTIONS:
        raise IngestError("card_copy.suggested_action is not one of the three actions")
    if not isinstance(copy.get("high_priority_review"), bool):
        raise IngestError("card_copy.high_priority_review must be a boolean")
    return copy


def _names_tool(row: dict) -> bool:
    return TOOL_CHOICE_RE.search(row_text(row)) is not None


def build_card_copy(
    row: dict,
    *,
    official: bool,
    independent_n: int,
    band: str,
    band_reason: str,
    edition: str,
) -> dict:
    """Sibling of score. Reads force_p0 already written on the row."""
    spec = row.get("force_p0") if isinstance(row.get("force_p0"), dict) else {}
    kinds = set(spec.get("kinds") or [])
    default = spec.get("default_action")
    high = bool(spec.get("active")) or band_reason == "review_p0"
    status = str(row.get("status_in_pool") or "")
    held = status == "deferred" or edition == "held_edition" or band_reason == "review_deferred"

    if official:
        evidence = "官方原始信息"
    elif independent_n >= 2:
        evidence = "多源确认"
    else:
        evidence = "尚待核实"

    names_tool = _names_tool(row)
    if high:
        if default == "skip":
            action = "暂缓"
        elif "runtime_vuln" in kinds or (names_tool and default == "promote"):
            action = "立即行动"
        else:
            action = "持续观察"
        if "runtime_vuln" in kinds:
            reason = VULN_REASON
        elif "frontier_launch" in kinds:
            reason = FRONTIER_REASON
        elif names_tool and default == "promote":
            reason = TOOL_REASON
        else:
            reason = QUEUE_REASON
    elif held:
        action = "暂缓"
        reason = HELD_REASON
    elif band == "drop":
        action = "暂缓"
        reason = DROP_REASON
    else:
        action = "持续观察"
        if official:
            reason = OFFICIAL_REASON
        elif independent_n >= 2:
            reason = MULTI_REASON
        else:
            reason = WATCH_REASON

    return _check(
        {
            "watch_reason": reason,
            "evidence_label": evidence,
            "suggested_action": action,
            "high_priority_review": high,
        }
    )


def self_check() -> None:
    official = public_auto_copy()
    _check(official)
    if official["suggested_action"] != "持续观察" or official["high_priority_review"]:
        raise SystemExit("FAIL: public auto copy must stay a watch, not a tool decision")
    row = {
        "status_in_pool": "active",
        "title": "FIXTURE",
        "snippet": "value=0.91 score 8.3",
        "force_p0": {
            "active": True,
            "kinds": ["frontier_launch"],
            "default_action": "promote",
            "tool_choice": True,
        },
    }
    preview = build_card_copy(
        row,
        official=False,
        independent_n=1,
        band="review",
        band_reason="review_p0",
        edition="eligible",
    )
    if preview["suggested_action"] != "持续观察" or not preview["high_priority_review"]:
        raise SystemExit(f"FAIL: research preview copy {preview}")
    if "0" in preview["watch_reason"] or "value" in preview["watch_reason"]:
        raise SystemExit("FAIL: preview reason leaked a number")
    vuln = dict(row)
    vuln["snippet"] = "Upgrade to 8.3.36"
    vuln["force_p0"] = {
        "active": True,
        "kinds": ["runtime_vuln"],
        "default_action": "promote",
        "tool_choice": True,
    }
    fixed = build_card_copy(
        vuln,
        official=False,
        independent_n=1,
        band="review",
        band_reason="review_p0",
        edition="eligible",
    )
    if fixed["suggested_action"] != "立即行动" or "8" in fixed["watch_reason"]:
        raise SystemExit(f"FAIL: vuln copy {fixed}")
    if not refuses_auto_publish({"force_p0": {"active": True}, "score": {"band": "auto_brief"}}):
        raise SystemExit("FAIL: active force_p0 must refuse auto publish")
    if not refuses_auto_publish({"card_copy": {"high_priority_review": True}}):
        raise SystemExit("FAIL: high_priority_review must refuse auto publish")
    if refuses_auto_publish({"score": {"band": "auto_brief", "band_reason": "auto_primary"}, "card_copy": official}):
        raise SystemExit("FAIL: ordinary auto copy must still publish")
    print("OK card_copy self-check")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Card copy helpers. No network.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    parser.error("pass --self-check")
    return 2


if __name__ == "__main__":
    sys.exit(main())
