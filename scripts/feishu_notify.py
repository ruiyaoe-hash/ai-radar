#!/usr/bin/env python3
"""Push formal (non-rumor) P0 cards to Feishu webhook; 24h health alert.

Requires secret FEISHU_BOT_WEBHOOK. If unset, prints what would be sent and exits 0.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
STATE = ROOT / "state.json"
TZ = timezone(timedelta(hours=8))
SITE = "https://ruiyaoe-hash.github.io/ai-radar/"


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def all_items():
    items = []
    for path in sorted(ARCHIVE.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.extend(data.get("items") or [])
    return items


def post_feishu(webhook: str, text: str) -> None:
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print("feishu status", resp.status, resp.read()[:200])


def main():
    webhook = (os.environ.get("FEISHU_BOT_WEBHOOK") or "").strip()
    items = all_items()
    now = datetime.now(TZ)
    st = load_state()
    notified = set(st.get("feishu_notified_ids") or [])

    formal_p0 = [
        it for it in items
        if it.get("priority") == "P0" and it.get("status") in {"confirmed", "multi_source"}
    ]
    new_p0 = [it for it in formal_p0 if it.get("id") not in notified]

    messages = []
    for it in new_p0:
        messages.append(
            "【AI Radar 正式 P0】{title}\n"
            "lens={lens} status={status}\n"
            "{url}\n"
            "id={eid}\n看板 {site}".format(
                title=it.get("title"),
                lens=it.get("lens"),
                status=it.get("status"),
                url=it.get("url") or SITE,
                eid=it.get("id"),
                site=SITE,
            )
        )

    # 24h health: any card with date+time within 24h?
    newest = None
    for it in items:
        date = it.get("date") or ""
        try:
            y, m, d = map(int, date.split("-"))
            t = it.get("time") or ""
            hh, mi = 12, 0
            if " " in t:
                hm = t.split(" ", 1)[1]
                hh, mi = map(int, hm.split(":"))
            dt = datetime(y, m, d, hh, mi, tzinfo=TZ)
            if newest is None or dt > newest:
                newest = dt
        except Exception:
            continue

    health_alert = False
    if newest is None or (now - newest) > timedelta(hours=24):
        health_alert = True
        lag = "无卡片" if newest is None else f"最新 {newest.isoformat()}（>{24}h）"
        messages.append(f"【AI Radar 健康告警】24h 无新卡。{lag}\n请检查 Alba digest / archive。")

    if not messages:
        print("nothing to notify")
        return

    for msg in messages:
        print("---")
        print(msg)
        if webhook:
            try:
                post_feishu(webhook, msg)
            except Exception as e:
                print("feishu error:", e)
                raise
        else:
            print("(FEISHU_BOT_WEBHOOK unset — dry run)")

    if webhook and new_p0:
        for it in new_p0:
            notified.add(it["id"])
        st["feishu_notified_ids"] = sorted(notified)
        st["last_feishu_run"] = now.isoformat()
        # Note: state.json commit is optional; Actions checkout is ephemeral.
        # Persist via repo only if a later step commits; for now write locally for logs.
        save_state(st)

    if health_alert and not webhook:
        print("health alert noted (no webhook)")


if __name__ == "__main__":
    main()
