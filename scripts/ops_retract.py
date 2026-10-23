#!/usr/bin/env python3
"""Dry-run retract or pause. Prints the next human step and does not edit files.

Does not commit, push, delete archive cards, or call Feishu.
Archive days are monotonic: a retract updates the original card in place.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
RUNBOOK = "docs/runbook-retract.md"
SHIFTS = {"08:00", "21:00"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def locate(card_id: str) -> list[str]:
    hits: list[str] = []
    if card_id.startswith("evt-"):
        for path in sorted(ARCHIVE.glob("????-??-??.json")):
            data = _load(path)
            for it in data.get("items") or []:
                if isinstance(it, dict) and it.get("id") == card_id:
                    hits.append(f"public/archive/{path.name}")
        return hits
    if card_id.startswith("prac-"):
        inbox = PUBLIC / "practice" / "inbox"
        if inbox.is_dir():
            for path in sorted(inbox.glob("*.json")):
                payload = _load(path)
                items = payload.get("items") if isinstance(payload, dict) and "items" in payload else (
                    payload if isinstance(payload, list) else [payload]
                )
                for it in items:
                    if isinstance(it, dict) and it.get("id") == card_id:
                        hits.append(f"public/practice/inbox/{path.name}")
        live = PUBLIC / "practice.json"
        if live.exists():
            for it in _load(live).get("items") or []:
                if isinstance(it, dict) and it.get("id") == card_id:
                    hits.append("public/practice.json")
        return hits
    return hits


def run(action: str, card_id: str, reason: str, shift: str, quiet: bool = False) -> int:
    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    action = action.strip().lower()
    card_id = card_id.strip()
    reason = reason.strip()
    shift = shift.strip()
    if action not in {"retract", "pause"}:
        say("FAIL ops: action 只能是 retract 或 pause")
        return 2
    if not reason:
        say("FAIL ops: reason 必填")
        return 2
    if shift and shift not in SHIFTS:
        say("FAIL ops: shift 只能是 08:00 或 21:00（13:30 已取消）")
        return 2
    say(f"ops dry-run: action={action}")
    say(f"reason: {reason}")
    say("本命令不改文件、不提交、不调用飞书。")
    if action == "pause":
        slot = shift or "（未指定，请写成 08:00 或 21:00）"
        say(f"暂停班次: {slot}")
        say("Alba 自行跳过这一班：不要写新卡，不要把本班当成已发布。")
        say("暂停原因记在飞书或私有池的主报里，不要写进公开仓的 DIGEST_LATEST.md。按 docs/AIHOT对接与表达规范-v0.md：一句一事，不要写 evt- 或 cand-。")
        say("不要更新 state.json（已弃用，见 TIMELINE）。")
        say("飞书订阅群若需要告知，由人发一句。不要改 FEISHU_BOT_WEBHOOK。")
        say("24 小时无新卡的健康检查仍可能响，本命令不会关掉它。")
        say(f"手册: {RUNBOOK}")
        return 0
    if not card_id.startswith(("evt-", "prac-")):
        say("FAIL ops: card_id 须以 evt- 或 prac- 开头")
        return 2
    hits = locate(card_id)
    if not hits:
        say(f"FAIL ops: 找不到 {card_id}")
        return 1
    say(f"card_id: {card_id}")
    for hit in hits:
        say(f"found: {hit}")
    if card_id.startswith("evt-"):
        say("不要删除归档条目，也不要删掉当天文件。校验要求归档只增不减。")
        say("在原卡上改正文，并写 correction.at 与 correction.note。")
        say("误升正式 P0：降低 priority 或改回 status，必要时写 previous_status。")
        say("侵权或事实错误：拿掉不宜公开的原文，改成下架说明，保留原来的 id。")
    else:
        say("从 public/practice/inbox/ 去掉该条，并从 public/practice.json 的 items 里去掉同一 id。")
        say("然后运行 python3 scripts/generate_derived.py。只删 inbox 不会把它从已派生的列表里拿掉。")
    say("批准人是主人。Alba 改完再提交。飞书群由人通知，不要改 webhook。")
    say(f"手册: {RUNBOOK}")
    return 0


def _first_event_id() -> str:
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        for it in _load(path).get("items") or []:
            eid = str(it.get("id") or "")
            if eid.startswith("evt-"):
                return eid
    return ""


def self_check() -> int:
    sample = _first_event_id()
    planted: Path | None = None
    if not sample:
        # Public archive may be empty after a slate reset. Plant a throwaway day
        # so retract-of-a-known-id still has something to find, then delete it.
        sample = "evt-20990101-ops-self-check"
        planted = ARCHIVE / "2099-01-01.json"
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        planted.write_text(
            json.dumps(
                {"date": "2099-01-01", "count": 1, "items": [{"id": sample}]},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    try:
        checks = (
            ("known retract", run("retract", sample, "self-check", "", quiet=True), 0),
            ("missing retract", run("retract", "evt-20261014-missing-card", "self-check", "", quiet=True), 1),
            ("pause", run("pause", "", "self-check skip", "21:00", quiet=True), 0),
            ("pause without reason", run("pause", "", "", "21:00", quiet=True), 2),
            ("retract without id", run("retract", "", "self-check", "", quiet=True), 2),
            ("removed midday", run("pause", "", "self-check", "13:30", quiet=True), 2),
        )
        for label, got, expect in checks:
            if got != expect:
                print(f"FAIL ops self-check {label}: got {got}, expect {expect}")
                return 1
    finally:
        if planted is not None:
            planted.unlink(missing_ok=True)
    print("OK ops retract/pause dry-run")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run retract or pause. Does not edit files.")
    parser.add_argument("--action", default=os.environ.get("OPS_ACTION", ""))
    parser.add_argument("--card-id", default=os.environ.get("OPS_CARD_ID", ""))
    parser.add_argument("--reason", default=os.environ.get("OPS_REASON", ""))
    parser.add_argument("--shift", default=os.environ.get("OPS_SHIFT", ""))
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    return run(args.action, args.card_id, args.reason, args.shift)


if __name__ == "__main__":
    sys.exit(main())
