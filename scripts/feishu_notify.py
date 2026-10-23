#!/usr/bin/env python3
"""Push formal (non-rumor) P0 cards to Feishu webhook; 24h health alert.

Also sends one short Chinese site-update ping per qualifying push to main.
The workflow sets FEISHU_SITE_SHA only on that push. Schedule and
workflow_dispatch leave it empty, so the 6h health run does not repeat the ping.
The same commit SHA is recorded in the notify cache after a successful post.

Requires secret FEISHU_BOT_WEBHOOK. If unset, prints what would be sent and exits 0.

AI_RADAR_P0_HOOK may point at a pool review/p0-YYYY-MM-DD.json. Those lines are a
review ping only. They are not archive writes, and they are not sent unless that
env var is set. The default workflow does not set it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ARCHIVE = PUBLIC / "archive"
# Actions sets FEISHU_STATE_PATH to a cached file so notified ids survive runs.
# Local default is a sidecar, not state.json (watermark must stay untouched).
STATE = Path(os.environ.get("FEISHU_STATE_PATH") or (ROOT / ".feishu-notify-state.json"))
TZ = timezone(timedelta(hours=8))
SITE = "https://ruiyaoe-hash.github.io/ai-radar/"
HEALTH_COOLDOWN = timedelta(hours=20)
SITE_UPDATE_LEAD = f"【AI Radar】公开站刚更新，去看看：{SITE}"
MAX_SITE_SHAS = 40
ZERO_SHA = "0" * 40
ARCHIVE_DAY = re.compile(r"public/archive/\d{4}-\d{2}-\d{2}\.json")


class _Unavailable:
    """Parent commit is not in this checkout, so addition counts would be a guess."""


UNAVAILABLE = _Unavailable()


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


def pool_hook_messages(path: Path) -> list[str]:
    """Read a pool review hook. Does not POST. Missing file returns no lines."""
    if not path.is_file():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"pool P0 hook unreadable: {exc}")
        return []
    lines = []
    for item in document.get("items") or []:
        lines.append(
            "【AI Radar 池内强制 P0 · 待人审】{kinds}\n"
            "建议={action}\n"
            "{url}\n"
            "id={cid} handle={handle}\n"
            "不写公开归档。要上今日必看仍走人工 PR。".format(
                kinds=",".join(item.get("kinds") or []),
                action=item.get("default_action") or "",
                url=item.get("url") or "",
                cid=item.get("id") or "",
                handle=item.get("handle") or "",
            )
        )
    return lines


def _norm_path(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if text.startswith("./"):
        text = text[2:]
    return text


def site_sha_pending(st: dict, sha: str) -> bool:
    """True when this push should get exactly one site ping."""
    sha = (sha or "").strip()
    if not sha or sha == ZERO_SHA:
        return False
    seen = {item for item in (st.get("feishu_site_shas") or []) if isinstance(item, str)}
    return sha not in seen


def remember_site_sha(st: dict, sha: str) -> None:
    sha = sha.strip()
    if not sha:
        return
    prev = [item for item in (st.get("feishu_site_shas") or []) if isinstance(item, str) and item and item != sha]
    prev.append(sha)
    st["feishu_site_shas"] = prev[-MAX_SITE_SHAS:]


def paths_from_push_event(event: dict) -> list[str]:
    """Union of added/modified/removed paths. Push payloads only; other events yield none."""
    if not isinstance(event, dict):
        return []
    found: list[str] = []
    seen: set[str] = set()
    for commit in event.get("commits") or []:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            names = commit.get(key) or []
            if not isinstance(names, list):
                continue
            for name in names:
                if not isinstance(name, str):
                    continue
                path = _norm_path(name)
                if path and path not in seen:
                    seen.add(path)
                    found.append(path)
    return found


def push_changed_paths() -> list[str]:
    raw = (os.environ.get("GITHUB_EVENT_PATH") or "").strip()
    if not raw:
        return []
    path = Path(raw)
    if not path.is_file():
        return []
    try:
        event = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"site update paths unreadable: {exc}")
        return []
    return paths_from_push_event(event)


def summarize_site_changes(paths: list[str]) -> str:
    """One short clause naming visitor surfaces. Empty when nothing recognizable changed."""
    archive_days: set[str] = set()
    index = briefs = items = today3 = practice = False
    tools = theses = feed = handbook = blog = False
    for raw in paths:
        path = _norm_path(raw)
        if ARCHIVE_DAY.fullmatch(path):
            archive_days.add(path)
        elif path == "public/archive/index.json" or path.startswith("public/archive/"):
            index = True
        elif path == "public/briefs.json":
            briefs = True
        elif path == "public/items.json":
            items = True
        elif path == "public/today3.txt":
            today3 = True
        elif path == "public/practice.json" or path.startswith("public/practice/inbox/"):
            practice = True
        elif path == "public/tools-radar.json":
            tools = True
        elif path == "public/theses.json":
            theses = True
        elif path == "public/feed.xml" or path.startswith("public/feeds/"):
            feed = True
        elif path.startswith("public/data/") or path.startswith("public/topics/"):
            handbook = True
        elif path.startswith("public/blog/") or path.startswith("content/posts/"):
            blog = True
    parts: list[str] = []
    if archive_days:
        parts.append(f"归档 {len(archive_days)} 天")
    elif index:
        parts.append("归档索引")
    if briefs:
        parts.append("快讯")
    if items:
        parts.append("看板")
    if today3:
        parts.append("今日三条")
    if practice:
        parts.append("做法")
    if tools:
        parts.append("工具")
    if theses:
        parts.append("论点")
    if feed:
        parts.append("订阅")
    if handbook:
        parts.append("手册")
    if blog:
        parts.append("随笔")
    if not parts:
        return ""
    return "改动：" + "、".join(parts)


def _item_ids(text: str | None) -> set[str]:
    if not text:
        return set()
    try:
        data = json.loads(text)
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    found = set()
    for item in data.get("items") or []:
        if isinstance(item, dict) and item.get("id"):
            found.add(str(item["id"]))
    return found


def added_item_ids(before_text: str | None, after_text: str | None) -> int:
    """How many item ids showed up. Missing before means the file is new."""
    return len(_item_ids(after_text) - _item_ids(before_text))


def revision_available(rev: str) -> bool:
    rev = (rev or "").strip()
    if not rev or rev == ZERO_SHA:
        return False
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{rev}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return False
    return proc.returncode == 0


def lookup_blob(rev: str, path: str):
    """File text, None if that commit lacks the path, or UNAVAILABLE if the commit is absent."""
    if not revision_available(rev):
        return UNAVAILABLE
    try:
        proc = subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return UNAVAILABLE
    if proc.returncode == 0:
        return proc.stdout
    if "does not exist" in (proc.stderr or "") or "exists on disk, but not in" in (proc.stderr or ""):
        return None
    return UNAVAILABLE


def count_additions(paths: list[str], before: str) -> tuple[int, int]:
    """New archive card ids and new brief ids. Unavailable parent → (0, 0), never a guess."""
    cards = 0
    briefs = 0
    seen: set[str] = set()
    for raw in paths:
        path = _norm_path(raw)
        if path in seen:
            continue
        seen.add(path)
        if ARCHIVE_DAY.fullmatch(path):
            kind = "cards"
        elif path == "public/briefs.json":
            kind = "briefs"
        else:
            continue
        blob = lookup_blob(before, path)
        if blob is UNAVAILABLE:
            continue
        current = ""
        file = ROOT / path
        if file.is_file():
            try:
                current = file.read_text(encoding="utf-8")
            except Exception:
                continue
        added = added_item_ids(None if blob is None else blob, current)
        if kind == "cards":
            cards += added
        else:
            briefs += added
    return cards, briefs


def format_site_update(paths: list[str], new_cards: int = 0, new_briefs: int = 0) -> str:
    summary = summarize_site_changes(paths)
    extra: list[str] = []
    if new_cards > 0:
        extra.append(f"新卡 {new_cards}")
    if new_briefs > 0:
        extra.append(f"新快讯 {new_briefs}")
    detail = ""
    if summary and extra:
        detail = summary + "；" + "、".join(extra)
    elif summary:
        detail = summary
    elif extra:
        detail = "、".join(extra)
    if not detail:
        return SITE_UPDATE_LEAD
    return SITE_UPDATE_LEAD + "\n" + detail


def self_check() -> None:
    sample = ROOT / "testdata" / "p0" / "hook-sample.json"
    if not sample.is_file():
        raise SystemExit(f"FAIL: missing {sample}")
    lines = pool_hook_messages(sample)
    if len(lines) != 1 or "待人审" not in lines[0] or "snippet" in lines[0]:
        raise SystemExit(f"FAIL: pool hook preview: {lines}")
    missing = pool_hook_messages(ROOT / "testdata" / "p0" / "does-not-exist.json")
    if missing:
        raise SystemExit("FAIL: missing hook should not invent messages")

    lead = "【AI Radar】公开站刚更新，去看看：https://ruiyaoe-hash.github.io/ai-radar/"
    if format_site_update([]) != lead:
        raise SystemExit("FAIL: site ping lead changed")
    sample_paths = [
        "public/archive/2026-10-23.json",
        "public/archive/2026-10-23.json",
        "public/briefs.json",
        "README.md",
    ]
    sample = format_site_update(sample_paths, new_cards=3, new_briefs=1)
    if sample != lead + "\n改动：归档 1 天、快讯；新卡 3、新快讯 1":
        raise SystemExit(f"FAIL: site ping sample: {sample}")
    if summarize_site_changes(["scripts/feishu_notify.py", "public/assets/radar.css"]):
        raise SystemExit("FAIL: non-visitor paths should not get a change line")
    if added_item_ids('{"items":[{"id":"a"}]}', '{"items":[{"id":"a"},{"id":"b"}]}') != 1:
        raise SystemExit("FAIL: added item count")
    if added_item_ids(None, '{"items":[{"id":"a"},{"id":"b"}]}') != 2:
        raise SystemExit("FAIL: new file should count every id")
    if added_item_ids("not-json", "still-not") != 0:
        raise SystemExit("FAIL: bad json should not invent additions")
    event_paths = paths_from_push_event({
        "commits": [
            {"added": ["public/briefs.json"], "modified": ["public/items.json"], "removed": []},
            {"added": ["public/briefs.json"], "modified": "skip", "removed": [1]},
        ]
    })
    if event_paths != ["public/briefs.json", "public/items.json"]:
        raise SystemExit(f"FAIL: push paths: {event_paths}")
    if paths_from_push_event({"schedule": "0 */6 * * *"}):
        raise SystemExit("FAIL: non-push payload should not invent paths")

    st: dict = {}
    if not site_sha_pending(st, "abc123") or site_sha_pending(st, "") or site_sha_pending(st, ZERO_SHA):
        raise SystemExit("FAIL: site sha gate")
    for i in range(MAX_SITE_SHAS + 1):
        remember_site_sha(st, f"s{i}")
    kept = st.get("feishu_site_shas") or []
    if len(kept) != MAX_SITE_SHAS or kept[0] != "s1" or kept[-1] != f"s{MAX_SITE_SHAS}":
        raise SystemExit(f"FAIL: site sha cap: {kept[:2]}..{kept[-2:]}")
    if site_sha_pending(st, f"s{MAX_SITE_SHAS}") or not site_sha_pending(st, "s0"):
        raise SystemExit("FAIL: site sha dedupe")

    if lookup_blob(ZERO_SHA, "scripts/feishu_notify.py") is not UNAVAILABLE:
        raise SystemExit("FAIL: zero sha must not count as a parent")
    blob = lookup_blob("HEAD", "scripts/feishu_notify.py")
    if not isinstance(blob, str) or "def self_check" not in blob:
        raise SystemExit("FAIL: expected to read feishu_notify.py at HEAD")
    if lookup_blob("HEAD", "public/no-such-feishu-path.json") is not None:
        raise SystemExit("FAIL: missing path in a real commit should count as new, not unavailable")
    if count_additions(["public/briefs.json"], ZERO_SHA) != (0, 0):
        raise SystemExit("FAIL: unavailable parent must not guess new briefs")

    workflow = (ROOT / ".github" / "workflows" / "feishu-and-health.yml").read_text(encoding="utf-8")
    for needle in (
        'cron: "0 */6 * * *"',
        "FEISHU_SITE_SHA",
        "FEISHU_SITE_BEFORE",
        "github.event_name == 'push' && github.sha",
        "github.event_name == 'push' && '0'",
        "public/archive/**",
        "public/briefs.json",
        "public/items.json",
        "public/today3.txt",
        "public/practice.json",
        "public/practice/inbox/**",
        "public/tools-radar.json",
        "public/theses.json",
        "public/feed.xml",
        "public/feeds/**",
        "public/data/**",
        "public/topics/**",
        "public/blog/**",
        "content/posts/**",
    ):
        if needle not in workflow:
            raise SystemExit(f"FAIL: feishu workflow missing {needle}")
    print("OK feishu_notify self-check")


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
    hook = (os.environ.get("AI_RADAR_P0_HOOK") or "").strip()
    if hook:
        # Review ping only. Does not mark archive ids, and does not publish cards.
        messages.extend(pool_hook_messages(Path(hook)))
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
                site=SITE + "today.html",
            )
        )

    # One site ping per qualifying push. Schedule and workflow_dispatch leave the SHA empty.
    site_sha = (os.environ.get("FEISHU_SITE_SHA") or "").strip()
    site_ping = False
    if site_sha_pending(st, site_sha):
        changed = push_changed_paths()
        before = (os.environ.get("FEISHU_SITE_BEFORE") or "").strip()
        try:
            new_cards, new_briefs = count_additions(changed, before)
        except Exception as exc:
            print(f"site update counts skipped: {exc}")
            new_cards, new_briefs = 0, 0
        messages.append(format_site_update(changed, new_cards=new_cards, new_briefs=new_briefs))
        site_ping = True
    elif site_sha:
        print(f"site update already sent for {site_sha}")

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

    health_alert = newest is None or (now - newest) > timedelta(hours=24)
    if health_alert:
        last_alert = st.get("last_health_alert")
        cooled = False
        if last_alert:
            try:
                prev = datetime.fromisoformat(last_alert)
                cooled = (now - prev) < HEALTH_COOLDOWN
            except Exception:
                cooled = False
        if cooled:
            print("health alert suppressed (cooldown)")
            health_alert = False
        else:
            lag = "无卡片" if newest is None else f"最新 {newest.isoformat()}（>24h）"
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
            print("(FEISHU_BOT_WEBHOOK unset — dry run, not marking ids sent)")

    if webhook:
        for it in new_p0:
            if it.get("id"):
                notified.add(it["id"])
        st["feishu_notified_ids"] = sorted(notified)
        st["last_feishu_run"] = now.isoformat()
        if health_alert:
            st["last_health_alert"] = now.isoformat()
        if site_ping:
            remember_site_sha(st, site_sha)
        save_state(st)
        print(f"wrote notify state {STATE}")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main()
