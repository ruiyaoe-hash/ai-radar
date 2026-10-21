#!/usr/bin/env python3
"""Build a raw X fetch for config.json practice_handles + a_tier.

The stable ingest path stays scripts/shift_ingest_x_to_pool.py --fetch.
This script only produces that JSON.

Without X_BEARER_TOKEN it exits 0 and writes nothing, so the hand-fed JSON
path keeps working. With the token it calls the X API v2 user timeline and
writes the shape ingest_x already accepts. The token is never printed.

  python3 scripts/fetch_x_watch.py --self-check
  python3 scripts/fetch_x_watch.py --dry-list
  X_BEARER_TOKEN=... python3 scripts/fetch_x_watch.py --out /tmp/x-fetch.json

GitHub Actions secret name: X_BEARER_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.x.com/2"
TWEET_FIELDS = "created_at,public_metrics,entities,note_tweet"
USER_FIELDS = "username"


def load_watch_handles(root: Path | None = None) -> list[str]:
    """practice_handles, then a_tier. Case-insensitive de-dupe, config spelling kept."""
    root = root or ROOT
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    ordered: list[str] = []
    seen: set[str] = set()
    for key in ("practice_handles", "a_tier"):
        values = cfg.get(key) or []
        if not isinstance(values, list):
            raise SystemExit(f"FAIL: config {key} must be a list")
        for raw in values:
            if not isinstance(raw, str) or not raw.strip():
                raise SystemExit(f"FAIL: config {key} has a non-string handle")
            handle = raw.strip().lstrip("@")
            folded = handle.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            ordered.append(handle)
    return ordered


def normalize_user_tweets(handle: str, payload: dict) -> list[dict]:
    """Map one user-tweets response into ingest_x items. Fixture-safe, no I/O."""
    if not isinstance(payload, dict):
        return []
    users = {}
    includes = payload.get("includes") if isinstance(payload.get("includes"), dict) else {}
    for user in includes.get("users") or []:
        if isinstance(user, dict) and user.get("id") is not None and user.get("username"):
            users[str(user["id"])] = str(user["username"])
    items = []
    data = payload.get("data") or []
    if isinstance(data, dict):
        data = [data]
    for tweet in data:
        if not isinstance(tweet, dict) or tweet.get("id") is None:
            continue
        author = users.get(str(tweet.get("author_id") or "")) or handle
        text = tweet.get("text")
        note = tweet.get("note_tweet")
        if isinstance(note, dict) and isinstance(note.get("text"), str) and note["text"].strip():
            text = note["text"]
        item = {
            "id": str(tweet["id"]),
            "text": text if isinstance(text, str) else "",
            "created_at": tweet.get("created_at"),
            "username": str(author).lstrip("@"),
            "url": f"https://x.com/{str(author).lstrip('@')}/status/{tweet['id']}",
        }
        metrics = tweet.get("public_metrics")
        if isinstance(metrics, dict):
            item["public_metrics"] = metrics
        items.append(item)
    return items


def _request(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "ai-radar-watch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:180]
        except Exception:
            detail = ""
        raise SystemExit(f"FAIL: X API HTTP {exc.code} for {urllib.parse.urlsplit(url).path} {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"FAIL: X API network error: {exc.reason}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: X API returned non-JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit("FAIL: X API payload was not an object")
    return payload


def fetch_handle(handle: str, token: str, max_results: int = 5) -> tuple[list[dict], str | None]:
    """Return items, or ( [], warning ). Does not print the token."""
    user_url = f"{API}/users/by/username/{urllib.parse.quote(handle)}?user.fields={USER_FIELDS}"
    try:
        user_payload = _request(user_url, token)
    except SystemExit as exc:
        return [], str(exc)
    data = user_payload.get("data") if isinstance(user_payload.get("data"), dict) else None
    if not data or data.get("id") is None:
        return [], f"WARN: no X user for @{handle}"
    user_id = str(data["id"])
    tweets_url = (
        f"{API}/users/{urllib.parse.quote(user_id)}/tweets"
        f"?max_results={max_results}&tweet.fields={TWEET_FIELDS}"
        f"&expansions=author_id&user.fields={USER_FIELDS}"
        "&exclude=retweets,replies"
    )
    try:
        tweets = _request(tweets_url, token)
    except SystemExit as exc:
        return [], str(exc)
    return normalize_user_tweets(str(data.get("username") or handle), tweets), None


def build_payload(handles: list[str], token: str) -> dict:
    items: list[dict] = []
    warnings = 0
    for index, handle in enumerate(handles):
        if index:
            time.sleep(0.2)
        batch, warning = fetch_handle(handle, token)
        if warning:
            warnings += 1
            print(warning, file=sys.stderr)
            continue
        items.extend(batch)
    if handles and warnings == len(handles):
        raise SystemExit("FAIL: every watch handle failed")
    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }


def self_check() -> None:
    """No network. Checks the watch list and the response normalizer."""
    handles = load_watch_handles(ROOT)
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    practice = {str(item).strip().lstrip("@").casefold() for item in cfg["practice_handles"]}
    tier = {str(item).strip().lstrip("@").casefold() for item in cfg["a_tier"]}
    folded = [item.casefold() for item in handles]
    if len(folded) != len(set(folded)):
        raise SystemExit("FAIL: watch list has a case-insensitive duplicate")
    if not practice <= set(folded) or not tier <= set(folded):
        raise SystemExit("FAIL: watch list dropped a practice or a_tier handle")
    if practice & tier:
        raise SystemExit("FAIL: practice_handles overlap a_tier")
    if folded[0] not in practice:
        raise SystemExit("FAIL: practice_handles should lead the watch list")

    payload = {
        "data": [
            {
                "id": "55",
                "text": "FIXTURE short",
                "created_at": "2026-10-14T01:00:00Z",
                "author_id": "1",
                "public_metrics": {"like_count": 3, "bookmark_count": 2, "impression_count": 9},
                "note_tweet": {"text": "FIXTURE note body"},
            }
        ],
        "includes": {"users": [{"id": "1", "username": "OpenAI"}]},
    }
    items = normalize_user_tweets("OpenAI", payload)
    if len(items) != 1:
        raise SystemExit(f"FAIL: normalizer wrote {len(items)} items")
    item = items[0]
    if item["url"] != "https://x.com/OpenAI/status/55":
        raise SystemExit(f"FAIL: url {item['url']}")
    if item["text"] != "FIXTURE note body":
        raise SystemExit("FAIL: note_tweet text was dropped")
    if item["public_metrics"]["bookmark_count"] != 2 or item["username"] != "OpenAI":
        raise SystemExit(f"FAIL: metrics/handle {item}")
    if normalize_user_tweets("nobody", {"data": []}) != []:
        raise SystemExit("FAIL: empty timeline should yield no items")

    # Hand path stays available: missing token must not pretend to fetch.
    import io
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout

    saved = os.environ.pop("X_BEARER_TOKEN", None)
    try:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main(["--dry-list"])
        if code != 0 or "59" not in out_buf.getvalue() and str(len(handles)) not in out_buf.getvalue():
            raise SystemExit(f"FAIL: dry-list exit {code}: {out_buf.getvalue()!r}")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fetch.json"
            skipped_out, skipped_err = io.StringIO(), io.StringIO()
            with redirect_stdout(skipped_out), redirect_stderr(skipped_err):
                skipped = main(["--out", str(out)])
            if skipped != 0 or out.exists():
                raise SystemExit("FAIL: missing token should exit 0 without writing a fetch")
            if "shift_ingest_x_to_pool.py" not in skipped_err.getvalue():
                raise SystemExit("FAIL: missing token did not keep the hand-feed path")
    finally:
        if saved is not None:
            os.environ["X_BEARER_TOKEN"] = saved
    print(f"OK fetch_x_watch self-check ({len(handles)} handles)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch watch-list posts into ingest_x JSON, or skip.")
    parser.add_argument("--out", help="Write the raw fetch JSON here.")
    parser.add_argument("--dry-list", action="store_true", help="Print handle count and exit. No network.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    handles = load_watch_handles(ROOT)
    if args.dry_list:
        print(f"OK fetch_x_watch: {len(handles)} handles (practice_handles + a_tier)")
        return 0
    token = (os.environ.get("X_BEARER_TOKEN") or "").strip()
    if not token:
        print(
            "X_BEARER_TOKEN 未配置。不抓取。手灌路径仍可用："
            "python3 scripts/shift_ingest_x_to_pool.py --fetch fetch.json --pool-dir ../ai-radar-pool",
            file=sys.stderr,
        )
        return 0
    if not args.out:
        parser.error("pass --out")
    payload = build_payload(handles, token)
    target = Path(args.out)
    public = (ROOT / "public").resolve()
    resolved = target.resolve()
    if resolved == public or public in resolved.parents:
        print("FAIL: refusing to write a fetch under public/", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK fetch_x_watch: {len(payload['items'])} items → {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
