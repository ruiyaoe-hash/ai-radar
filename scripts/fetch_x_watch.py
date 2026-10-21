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
USERS_PER_LOOKUP = 100
MAX_RATE_WAIT = 90.0


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


class FetchError(Exception):
    """One request failed. The message never contains the token."""


class RateLimited(FetchError):
    def __init__(self, message: str, wait_seconds: float | None) -> None:
        super().__init__(message)
        self.wait_seconds = wait_seconds


def _wait_from_headers(headers, now: float) -> float | None:
    if headers is None:
        return None
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    reset = headers.get("x-rate-limit-reset")
    if reset:
        try:
            return max(0.0, float(reset) - now)
        except ValueError:
            pass
    return None


def http_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "ai-radar-watch/1.0",
        },
    )
    path = urllib.parse.urlsplit(url).path
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"X API 429 for {path}", _wait_from_headers(exc.headers, time.time())) from exc
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:180]
        except Exception:
            detail = ""
        raise FetchError(f"X API HTTP {exc.code} for {path} {detail}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"X API network error: {exc.reason}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError(f"X API returned non-JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise FetchError("X API payload was not an object")
    return payload


class Client:
    """Wraps a getter with one bounded wait on 429. After a second 429 the run stops asking."""

    def __init__(self, token: str, getter=http_get, sleep=time.sleep, max_wait: float = MAX_RATE_WAIT) -> None:
        self.token = token
        self.getter = getter
        self.sleep = sleep
        self.max_wait = max_wait
        self.exhausted = False

    def get(self, url: str) -> dict:
        if self.exhausted:
            raise RateLimited("X API rate limit already hit this run", None)
        try:
            return self.getter(url, self.token)
        except RateLimited as exc:
            wait = exc.wait_seconds
            if wait is None or wait > self.max_wait:
                self.exhausted = True
                raise
            self.sleep(wait + 1)
            try:
                return self.getter(url, self.token)
            except RateLimited:
                self.exhausted = True
                raise


def load_state(path: Path | None) -> dict:
    empty = {"users": {}, "since": {}}
    if path is None or not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict):
        return empty
    users = data.get("users") if isinstance(data.get("users"), dict) else {}
    since = data.get("since") if isinstance(data.get("since"), dict) else {}
    return {
        "users": {str(k): str(v) for k, v in users.items() if str(v).isdigit()},
        "since": {str(k): str(v) for k, v in since.items() if str(v).isdigit()},
    }


def resolve_users(handles: list[str], client: Client, cached: dict[str, str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """casefolded handle → (user id, username). Unknown handles are looked up 100 at a time."""
    resolved: dict[str, tuple[str, str]] = {}
    missing = []
    for handle in handles:
        uid = cached.get(handle.casefold())
        if uid:
            resolved[handle.casefold()] = (uid, handle)
        else:
            missing.append(handle)
    warnings = []
    for start in range(0, len(missing), USERS_PER_LOOKUP):
        chunk = missing[start : start + USERS_PER_LOOKUP]
        url = f"{API}/users/by?usernames={urllib.parse.quote(','.join(chunk), safe=',')}&user.fields={USER_FIELDS}"
        try:
            payload = client.get(url)
        except FetchError as exc:
            warnings.extend(f"WARN: @{handle}: {exc}" for handle in chunk)
            continue
        found = set()
        for user in payload.get("data") or []:
            if isinstance(user, dict) and user.get("id") is not None and user.get("username"):
                folded = str(user["username"]).casefold()
                resolved[folded] = (str(user["id"]), str(user["username"]))
                found.add(folded)
        warnings.extend(f"WARN: no X user for @{handle}" for handle in chunk if handle.casefold() not in found)
    return resolved, warnings


def fetch_timeline(user_id: str, username: str, client: Client, since_id: str | None, max_results: int = 5) -> list[dict]:
    url = (
        f"{API}/users/{urllib.parse.quote(user_id)}/tweets"
        f"?max_results={max_results}&tweet.fields={TWEET_FIELDS}"
        f"&expansions=author_id&user.fields={USER_FIELDS}"
        "&exclude=retweets,replies"
    )
    if since_id:
        url += f"&since_id={urllib.parse.quote(since_id)}"
    return normalize_user_tweets(username, client.get(url))


def _max_id(items: list[dict], current: str | None) -> str | None:
    best = int(current) if current and current.isdigit() else None
    for item in items:
        raw = str(item.get("id") or "")
        if raw.isdigit() and (best is None or int(raw) > best):
            best = int(raw)
    return str(best) if best is not None else None


def build_payload(handles: list[str], client: Client, state: dict, pause: float = 0.2) -> tuple[dict, dict, int]:
    """Returns (fetch JSON, new state, failed handle count). Raises when every handle failed."""
    resolved, warnings = resolve_users(handles, client, state["users"])
    for warning in warnings:
        print(warning, file=sys.stderr)
    failed = len(warnings)
    users = dict(state["users"])
    since = dict(state["since"])
    items: list[dict] = []
    for index, handle in enumerate(handles):
        entry = resolved.get(handle.casefold())
        if entry is None:
            continue
        user_id, username = entry
        users[handle.casefold()] = user_id
        if index and pause:
            client.sleep(pause)
        try:
            batch = fetch_timeline(user_id, username, client, since.get(user_id))
        except FetchError as exc:
            failed += 1
            print(f"WARN: @{handle}: {exc}", file=sys.stderr)
            continue
        newest = _max_id(batch, since.get(user_id))
        if newest:
            since[user_id] = newest
        items.extend(batch)
    if handles and failed >= len(handles):
        raise FetchError("every watch handle failed")
    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }
    return payload, {"users": users, "since": since}, failed


def _refuse_public(path: Path) -> None:
    public = (ROOT / "public").resolve()
    resolved = path.resolve()
    if resolved == public or public in resolved.parents:
        raise FetchError(f"refusing to write under public/: {path}")


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

    _offline_client_checks()
    print(f"OK fetch_x_watch self-check ({len(handles)} handles)")


def _offline_client_checks() -> None:
    import tempfile

    calls: list[str] = []
    slept: list[float] = []
    limited = {"once": True}

    def fake_get(url: str, token: str) -> dict:
        if token != "FIXTURE-TOKEN":
            raise SystemExit("FAIL: client did not pass the token to the getter")
        calls.append(url)
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        if parts.path.endswith("/users/by"):
            names = query["usernames"][0].split(",")
            return {"data": [{"id": str(100 + i), "username": name} for i, name in enumerate(names) if name != "ghost"]}
        uid = parts.path.split("/")[-2]
        if uid == "101" and limited["once"]:
            limited["once"] = False
            raise RateLimited("X API 429 for fixture", 3)
        if uid == "102":
            raise FetchError("X API HTTP 503 for fixture")
        return {
            "data": [{"id": f"{uid}9", "text": "FIXTURE", "created_at": "2026-10-14T01:00:00Z", "author_id": uid}],
            "includes": {"users": [{"id": uid, "username": f"u{uid}"}]},
        }

    handles = ["alpha", "beta", "gamma", "ghost"]
    client = Client("FIXTURE-TOKEN", getter=fake_get, sleep=slept.append)
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state" / "x-since.json"
        out = Path(tmp) / "fetch.json"
        code = run_fetch(handles, client, out, state_path)
        if code != 2:
            raise SystemExit(f"FAIL: partial fetch should exit 2, got {code}")
        lookups = [url for url in calls if "/users/by?" in url]
        if len(lookups) != 1 or "alpha,beta,gamma,ghost" not in lookups[0]:
            raise SystemExit(f"FAIL: users were not looked up in one batch {lookups}")
        if 4 not in slept:
            raise SystemExit(f"FAIL: Retry-After was not honored {slept}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["users"] != {"alpha": "100", "beta": "101", "gamma": "102"}:
            raise SystemExit(f"FAIL: user id cache {state['users']}")
        if state["since"] != {"100": "1009", "101": "1019"}:
            raise SystemExit(f"FAIL: since_id state {state['since']}")
        if len(json.loads(out.read_text(encoding="utf-8"))["items"]) != 2:
            raise SystemExit("FAIL: partial fetch dropped the items that did come back")

        calls.clear()
        again = run_fetch(["alpha"], Client("FIXTURE-TOKEN", getter=fake_get, sleep=slept.append), out, state_path)
        if again != 0 or any("/users/by?" in url for url in calls):
            raise SystemExit("FAIL: cached user id was looked up again")
        if "since_id=1009" not in calls[0]:
            raise SystemExit(f"FAIL: since_id was not sent {calls}")

    def always_limited(url: str, token: str) -> dict:
        raise RateLimited("X API 429 for fixture", 900)

    stopped = Client("FIXTURE-TOKEN", getter=always_limited, sleep=slept.append)
    with tempfile.TemporaryDirectory() as tmp:
        if run_fetch(["alpha", "beta"], stopped, Path(tmp) / "f.json", None) != 1:
            raise SystemExit("FAIL: a run with nothing fetched should exit 1")
    if not stopped.exhausted:
        raise SystemExit("FAIL: a long Retry-After should stop the run instead of sleeping")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _refuse_public(ROOT / "public" / "x-since.json")
        except FetchError:
            pass
        else:
            raise SystemExit("FAIL: state under public/ was accepted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch watch-list posts into ingest_x JSON, or skip.")
    parser.add_argument("--out", help="Write the raw fetch JSON here.")
    parser.add_argument("--state", help="Private JSON with cached user ids and since_id per account. Not under public/.")
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
    return run_fetch(handles, Client(token), Path(args.out), Path(args.state) if args.state else None)


def run_fetch(handles: list[str], client: Client, target: Path, state_path: Path | None) -> int:
    """0 = every handle answered, 2 = partial (what came back is written), 1 = nothing usable."""
    try:
        _refuse_public(target)
        if state_path is not None:
            _refuse_public(state_path)
        payload, state, failed = build_payload(handles, client, load_state(state_path))
    except FetchError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if state_path is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK fetch_x_watch: {len(payload['items'])} items → {target}; failed handles {failed}/{len(handles)}")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
