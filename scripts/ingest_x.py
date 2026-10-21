#!/usr/bin/env python3
"""Deterministic X fetch → candidate-pool JSONL.

Alba does not hand-author pool rows. Pass the raw fetch JSON on stdin or
with --input. This script normalizes the permalink, assigns a stable cid,
and writes every item. It does not score, rank, or drop posts that a later
gate would BLOCK. Judgment fields stay null and status_in_pool is pending.

  python3 scripts/ingest_x.py --input fetch.json --out /tmp/batch.jsonl \\
      --ingested-at 2026-10-14T00:05:00Z

  python3 scripts/ingest_x.py --pool-dir ../ai-radar-pool < fetch.json

--out overwrites a local JSONL file (CI fixtures and inspection). Every input
item becomes one line, including repeated status ids.

--pool-dir merges into {pool-dir}/candidates/YYYY-MM-DD.jsonl. The date is the
Asia/Shanghai calendar day of ingested_at. Rows whose id is already in that
file are left untouched, so a re-run does not wipe judgment fields. Same-batch
duplicates that are not yet in the file are all written.

Production writes belong in the private ai-radar-pool repo, checked out in
Actions with a token scoped to that repo. This script only writes the path
you pass. It refuses to write under public/. The public CI job does not
have the private checkout.

Exit 0 when every item became a row. Exit 2 when some items had no permalink
or status id: those are FETCH_GAP lines on stderr, and the identifiable rows
are still written. Exit 1 on usage or parse errors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import parse_source_timestamp, utc_now_iso
else:
    from .card_times import parse_source_timestamp, utc_now_iso

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc

X_HOSTS = {
    "x.com",
    "twitter.com",
    "mobile.x.com",
    "mobile.twitter.com",
    "www.x.com",
    "www.twitter.com",
    "vxtwitter.com",
    "fxtwitter.com",
}
LIST_KEYS = ("items", "data", "posts", "tweets", "results")
GENERAL_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "si"}
X_TRACKING = GENERAL_TRACKING | {"s", "t", "ref_src", "ref_url", "src", "cn", "ref"}
CANDIDATE_ID_RE_DAY = __import__("re").compile(r"^[0-9]{8}$")


class IngestError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def candidate_id(stable_key: str, day_yyyymmdd: str) -> str:
    """cid = cand-{Shanghai day}-{sha256(stable_key)[:12]}."""
    if not CANDIDATE_ID_RE_DAY.match(day_yyyymmdd):
        raise IngestError(f"bad candidate day {day_yyyymmdd!r}")
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:12]
    return f"cand-{day_yyyymmdd}-{digest}"


def dumps_record(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_utc(value: str) -> datetime:
    parsed = parse_source_timestamp(value)
    if not parsed:
        raise IngestError(f"not an ISO-8601 UTC timestamp: {value!r}")
    iso = parsed[:-1] + "+00:00" if parsed.endswith("Z") else parsed
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        raise IngestError(f"timestamp needs a timezone: {value!r}")
    return dt.astimezone(UTC)


def shanghai_day(value: str) -> str:
    """YYYYMMDD in Asia/Shanghai."""
    return parse_utc(value).astimezone(SHANGHAI).strftime("%Y%m%d")


def shanghai_file_day(value: str) -> str:
    """YYYY-MM-DD in Asia/Shanghai. Pool file name."""
    return parse_utc(value).astimezone(SHANGHAI).strftime("%Y-%m-%d")


def clean_handle(value) -> str | None:
    if not isinstance(value, str):
        return None
    handle = value.strip().lstrip("@")
    if not handle or any(ch in handle for ch in " /?#"):
        return None
    return handle.lower()


def dig(obj, *keys):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _status_from_path(path: str) -> tuple[str | None, str | None]:
    segs = [part for part in path.split("/") if part]
    if (
        len(segs) >= 4
        and segs[0].lower() == "i"
        and segs[1].lower() == "web"
        and segs[2].lower() == "status"
        and segs[3].isdigit()
    ):
        return None, segs[3]
    if len(segs) >= 3 and segs[0].lower() == "i" and segs[1].lower() == "status" and segs[2].isdigit():
        return None, segs[2]
    if len(segs) >= 3 and segs[1].lower() in {"status", "statuses"} and segs[2].isdigit():
        return segs[0], segs[2]
    return None, None


def normalize_url(url: str, handle_hint: str | None = None) -> str | None:
    """Canonical https URL. X status links collapse to x.com/{handle}/status/{id}."""
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower()
    is_x = host in X_HOSTS
    path_handle, status_id = _status_from_path(urllib.parse.unquote(parts.path))
    if is_x and status_id:
        handle = clean_handle(path_handle) or clean_handle(handle_hint)
        if handle:
            return f"https://x.com/{handle}/status/{status_id}"
        return f"https://x.com/i/status/{status_id}"

    tracking = X_TRACKING if is_x else GENERAL_TRACKING
    filtered = []
    for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in tracking:
            continue
        filtered.append((key, val))
    filtered.sort()
    query = urllib.parse.urlencode(filtered, doseq=True)
    path = urllib.parse.unquote(parts.path or "")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    out_host = "x.com" if is_x else host
    return urllib.parse.urlunsplit(("https", out_host, path, query, ""))


def status_id_of(url: str | None) -> str | None:
    if not url:
        return None
    _handle, status_id = _status_from_path(urllib.parse.urlsplit(url).path)
    return status_id


def numeric_id(value) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return value
    return None


def index_users(payload) -> dict[str, str]:
    users: dict[str, str] = {}
    if not isinstance(payload, dict):
        return users
    includes = payload.get("includes")
    if not isinstance(includes, dict):
        return users
    for user in includes.get("users") or []:
        if not isinstance(user, dict) or user.get("id") is None:
            continue
        handle = clean_handle(user.get("username") or user.get("screen_name"))
        if handle:
            users[str(user["id"])] = handle
    return users


def coerce_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise IngestError("fetch JSON must be an object or a list")
    for key in LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if key == "data" and isinstance(value, dict):
            return [value]
    if any(key in payload for key in ("id", "id_str", "rest_id", "text", "full_text", "url")):
        return [payload]
    raise IngestError(
        "unrecognized X fetch shape; expected a list or items/data/posts/tweets"
    )


def extract_handle(item: dict, users: dict[str, str]) -> str | None:
    for key in ("handle", "username", "screen_name"):
        handle = clean_handle(item.get(key))
        if handle:
            return handle
    author = item.get("author")
    if isinstance(author, str):
        handle = clean_handle(author)
        if handle:
            return handle
    if isinstance(author, dict):
        for key in ("username", "userName", "screen_name", "handle"):
            handle = clean_handle(author.get(key))
            if handle:
                return handle
    user = item.get("user")
    if isinstance(user, dict):
        for key in ("username", "screen_name", "handle"):
            handle = clean_handle(user.get(key))
            if handle:
                return handle
    for path in (
        ("core", "user_results", "result", "legacy", "screen_name"),
        ("core", "user_results", "result", "core", "screen_name"),
        ("legacy", "user", "screen_name"),
    ):
        handle = clean_handle(dig(item, *path))
        if handle:
            return handle
    author_id = item.get("author_id")
    if author_id is not None and str(author_id) in users:
        return users[str(author_id)]
    return None


def extract_text(item: dict) -> str | None:
    for path in (
        ("text",),
        ("full_text",),
        ("note_tweet", "text"),
        ("note_tweet", "note_tweet_results", "result", "text"),
        ("legacy", "full_text"),
        ("legacy", "text"),
    ):
        value = dig(item, *path)
        if isinstance(value, str) and value.strip():
            return value.replace("\r\n", "\n").strip()
    return None


def _nonneg_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _count_from(mapping: dict, *keys: str) -> int | None:
    for key in keys:
        if key not in mapping:
            continue
        found = _nonneg_int(mapping.get(key))
        if found is not None:
            return found
    return None


def extract_engagement(item: dict, captured_at: str | None = None) -> dict | None:
    """Copy like/bookmark counts when the raw fetch has them. Omit the object otherwise."""
    bags: list[dict] = []
    if isinstance(item, dict):
        bags.append(item)
        for key in ("public_metrics", "metrics", "organic_metrics"):
            bag = item.get(key)
            if isinstance(bag, dict):
                bags.append(bag)
        legacy = item.get("legacy")
        if isinstance(legacy, dict):
            bags.append(legacy)
    fields = {
        "likes": ("like_count", "likes", "favorite_count"),
        "bookmarks": ("bookmark_count", "bookmarks"),
        "reposts": ("retweet_count", "repost_count", "reposts"),
        "replies": ("reply_count", "replies"),
        "quotes": ("quote_count", "quotes"),
        "views": ("impression_count", "view_count", "views"),
    }
    found: dict = {}
    for name, keys in fields.items():
        for bag in bags:
            count = _count_from(bag, *keys)
            if count is not None:
                found[name] = count
                break
    if not found:
        return None
    if captured_at:
        found["captured_at"] = captured_at
    return found


def extract_created_at(item: dict) -> str | None:
    for path in (("created_at",), ("legacy", "created_at"), ("tweet", "created_at")):
        parsed = parse_source_timestamp(dig(item, *path))
        if parsed:
            return parsed
    return None


def extract_explicit_url(item: dict) -> str | None:
    for key in ("url", "tweet_url", "permalink", "twitter_url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for path in (("legacy", "url"), ("tweet", "url")):
        value = dig(item, *path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_status_id(item: dict, explicit_url: str | None) -> str | None:
    from_url = status_id_of(explicit_url) if explicit_url else None
    if explicit_url and from_url is None:
        normalized = normalize_url(explicit_url)
        from_url = status_id_of(normalized)
    for path in (("id",), ("id_str",), ("rest_id",), ("tweet_id",), ("legacy", "id_str")):
        found = numeric_id(dig(item, *path))
        if found:
            return from_url or found
    return from_url


def skeleton(
    record_id: str,
    url_norm: str,
    ingested_at: str,
    handle: str | None,
    published_at: str | None,
    snippet: str | None,
    title: str | None,
    channel: str = "x",
) -> dict:
    """Pending pool row. Judgment stays empty. channel is x, rss, or web."""
    if channel not in {"x", "rss", "web"}:
        raise IngestError(f"unsupported channel {channel!r}")
    return {
        "schema_version": 1,
        "id": record_id,
        "url": url_norm,
        "url_norm": url_norm,
        "title": title if isinstance(title, str) and title.strip() else None,
        "snippet": snippet,
        "published_at": published_at,
        "ingested_at": ingested_at,
        "source": {
            "channel": channel,
            "handle": handle,
            "role_guess": None,
        },
        "tier_prior": None,
        "participation": None,
        "lane_hint": None,
        "prefilter": None,
        "cluster_id": None,
        "status_in_pool": "pending",
        "drop_reason": None,
        "archive_id": None,
        "promotion_path": None,
        "notes": "",
    }


def item_to_record(item, ingested_at: str, users: dict[str, str]) -> tuple[dict | None, str | None]:
    if not isinstance(item, dict):
        return None, "not_object"
    handle = extract_handle(item, users)
    explicit = extract_explicit_url(item)
    status_id = extract_status_id(item, explicit)
    url_norm = None
    if explicit:
        url_norm = normalize_url(explicit, handle)
    if status_id and (url_norm is None or status_id_of(url_norm) != status_id):
        url_norm = normalize_url(
            f"https://x.com/{handle}/status/{status_id}" if handle else f"https://x.com/i/status/{status_id}",
            handle,
        )
        status_id = status_id_of(url_norm) or status_id
    if not url_norm:
        return None, "no_identity"
    if status_id:
        stable_key = f"x-status:{status_id}"
    else:
        stable_key = f"url:{url_norm}"
    published_at = extract_created_at(item)
    day_source = published_at or ingested_at
    title = item.get("title") if isinstance(item.get("title"), str) else None
    record = skeleton(
        candidate_id(stable_key, shanghai_day(day_source)),
        url_norm,
        ingested_at,
        handle,
        published_at,
        extract_text(item),
        title,
    )
    engagement = extract_engagement(item, ingested_at)
    if engagement:
        record["engagement"] = engagement
    return record, None


def records_from_payload(payload, ingested_at: str) -> tuple[list[dict], list[str]]:
    users = index_users(payload)
    records: list[dict] = []
    gaps: list[str] = []
    for index, item in enumerate(coerce_items(payload)):
        record, reason = item_to_record(item, ingested_at, users)
        if reason or record is None:
            gaps.append(f"FETCH_GAP index={index} reason={reason or 'no_identity'}")
            continue
        records.append(record)
    return records, gaps


def resolve_ingested_at(payload, override: str | None) -> str:
    if override:
        parsed = parse_source_timestamp(override)
        if not parsed:
            raise IngestError(f"--ingested-at is not ISO-8601 UTC: {override!r}")
        return parsed
    if isinstance(payload, dict):
        for key in ("ingested_at", "fetched_at", "fetchedAt"):
            parsed = parse_source_timestamp(payload.get(key))
            if parsed:
                return parsed
    return utc_now_iso()


def assert_not_public(path: Path) -> None:
    public = (ROOT / "public").resolve()
    resolved = path.resolve()
    if resolved == public or public in resolved.parents:
        raise IngestError(f"refusing to write candidate pool output under public/: {path}")


def write_batch(path: Path, records: list[dict]) -> None:
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(dumps_record(record) + "\n" for record in records)
    path.write_text(body, encoding="utf-8")


def merge_pool(pool_dir: Path, records: list[dict], ingested_at: str) -> tuple[Path, int, int]:
    assert_not_public(pool_dir)
    day = shanghai_file_day(ingested_at)
    path = pool_dir / "candidates" / f"{day}.jsonl"
    assert_not_public(path)
    file_ids: set[str] = set()
    lines: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            lines.append(line)
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(existing, dict) and isinstance(existing.get("id"), str):
                file_ids.add(existing["id"])
    added = 0
    kept = 0
    for record in records:
        if record["id"] in file_ids:
            kept += 1
            continue
        lines.append(dumps_record(record))
        added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return path, added, kept


def load_payload(path: str | None):
    if path:
        raw = Path(path).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        raise IngestError("empty fetch JSON")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IngestError(f"fetch JSON: {exc}") from exc


def run_ingest(payload, ingested_at: str, out: Path | None, pool_dir: Path | None) -> int:
    records, gaps = records_from_payload(payload, ingested_at)
    notes: list[str] = []
    if out is not None:
        write_batch(out, records)
        notes.append(f"wrote {len(records)} rows to {out}")
    if pool_dir is not None:
        path, added, kept = merge_pool(pool_dir, records, ingested_at)
        notes.append(f"pool {path} added={added} kept={kept} (existing ids are not overwritten)")
    for gap in gaps:
        print(gap, file=sys.stderr)
    if gaps:
        print(
            f"INGEST incomplete: rows={len(records)} gaps={len(gaps)}",
            file=sys.stderr,
        )
        return 2
    for note in notes:
        print(f"OK ingest_x: {note}")
    return 0


def self_check() -> None:
    """Fixture and invariant checks. Uses synthetic text only."""
    sample = ROOT / "testdata" / "x-fetch" / "sample.json"
    if not sample.is_file():
        raise SystemExit(f"FAIL: missing {sample}")
    payload = json.loads(sample.read_text(encoding="utf-8"))
    ingested = "2026-10-14T00:05:00Z"
    first, gaps = records_from_payload(payload, ingested)
    second, _ = records_from_payload(payload, ingested)
    if gaps:
        raise SystemExit(f"FAIL: sample fetch gaps: {gaps}")
    if [dumps_record(row) for row in first] != [dumps_record(row) for row in second]:
        raise SystemExit("FAIL: ingest is not deterministic")
    if len(first) != 4:
        raise SystemExit(f"FAIL: sample wrote {len(first)} rows, expected 4 (no hand filtering)")
    if any(row["status_in_pool"] != "pending" or row["drop_reason"] is not None for row in first):
        raise SystemExit("FAIL: ingest must leave judgment empty and status pending")
    if any(row["prefilter"] is not None or row["participation"] is not None for row in first):
        raise SystemExit("FAIL: ingest filled a judgment field")
    dup = [row for row in first if row["snippet"] == "FIXTURE official note alpha"]
    if len(dup) != 2 or dup[0]["id"] != dup[1]["id"]:
        raise SystemExit("FAIL: same status id must share a cid and still emit every row")
    if dup[0]["url_norm"] != "https://x.com/examplelab/status/1001":
        raise SystemExit(f"FAIL: url_norm {dup[0]['url_norm']!r}")
    expected_cid = candidate_id("x-status:1001", "20261014")
    if dup[0]["id"] != expected_cid:
        raise SystemExit(f"FAIL: cid {dup[0]['id']} != {expected_cid}")
    blocked = [row for row in first if "later gate would block" in (row["snippet"] or "")]
    if len(blocked) != 1:
        raise SystemExit("FAIL: a future BLOCK item was not written")
    cjk = [row for row in first if row["snippet"] and row["snippet"].startswith("夹具")]
    if len(cjk) != 1:
        raise SystemExit("FAIL: synthetic CJK snippet was dropped")

    variant_a = normalize_url("https://twitter.com/ExampleLab/status/1001?utm_source=test&s=20")
    variant_b = normalize_url("https://x.com/i/web/status/1001#ignored", "ExampleLab")
    variant_c = normalize_url("https://mobile.twitter.com/ExampleLab/statuses/1001/")
    if not (variant_a == variant_b == variant_c == "https://x.com/examplelab/status/1001"):
        raise SystemExit(f"FAIL: status normalize {variant_a} {variant_b} {variant_c}")
    article = normalize_url("https://Example.com/A/b/?utm_source=x&id=1")
    if article != "https://example.com/A/b?id=1":
        raise SystemExit(f"FAIL: article normalize {article!r}")

    v2 = {
        "data": [
            {
                "id": "555",
                "text": "FIXTURE v2",
                "created_at": "2026-10-14T03:00:00.000Z",
                "author_id": "9",
            }
        ],
        "includes": {"users": [{"id": "9", "username": "ExampleLab", "name": "Example Lab"}]},
    }
    v2_rows, v2_gaps = records_from_payload(v2, ingested)
    if v2_gaps or v2_rows[0]["url_norm"] != "https://x.com/examplelab/status/555":
        raise SystemExit(f"FAIL: twitter v2 shape {v2_rows} {v2_gaps}")
    if v2_rows[0]["id"] != candidate_id("x-status:555", "20261014"):
        raise SystemExit("FAIL: v2 cid")

    legacy = {
        "items": [
            {
                "rest_id": "777",
                "legacy": {
                    "full_text": "FIXTURE legacy",
                    "created_at": "Wed Oct 14 04:00:00 +0000 2026",
                },
                "core": {
                    "user_results": {
                        "result": {"legacy": {"screen_name": "ExampleLab"}}
                    }
                },
            }
        ]
    }
    legacy_rows, legacy_gaps = records_from_payload(legacy, ingested)
    if legacy_gaps or legacy_rows[0]["source"]["handle"] != "examplelab":
        raise SystemExit(f"FAIL: legacy shape {legacy_rows} {legacy_gaps}")
    if legacy_rows[0]["published_at"] != "2026-10-14T04:00:00Z":
        raise SystemExit(f"FAIL: legacy created_at {legacy_rows[0]['published_at']!r}")

    metrics_rows, metrics_gaps = records_from_payload(
        {
            "items": [
                {
                    "id": "88",
                    "text": "FIXTURE metrics",
                    "created_at": "2026-10-14T01:00:00Z",
                    "username": "examplelab",
                    "public_metrics": {
                        "like_count": 10,
                        "bookmark_count": 4,
                        "retweet_count": 1,
                        "reply_count": 0,
                        "impression_count": 100,
                    },
                }
            ]
        },
        ingested,
    )
    if metrics_gaps or "engagement" not in metrics_rows[0]:
        raise SystemExit(f"FAIL: engagement was not copied: {metrics_rows} {metrics_gaps}")
    engagement = metrics_rows[0]["engagement"]
    if engagement.get("likes") != 10 or engagement.get("bookmarks") != 4 or engagement.get("views") != 100:
        raise SystemExit(f"FAIL: engagement counts {engagement}")
    if any("engagement" in row for row in first):
        raise SystemExit("FAIL: sample rows without metrics must omit engagement")

    gap_rows, gap_msgs = records_from_payload(
        {"items": [{"text": "no identity"}, {"id": "42", "text": "FIXTURE kept"}]},
        ingested,
    )
    if len(gap_rows) != 1 or len(gap_msgs) != 1 or "reason=no_identity" not in gap_msgs[0]:
        raise SystemExit(f"FAIL: fetch gap handling {gap_rows} {gap_msgs}")

    late = "2026-10-14T16:30:00Z"
    if shanghai_file_day(late) != "2026-10-15":
        raise SystemExit("FAIL: pool file day should follow Asia/Shanghai")
    if shanghai_file_day(ingested) != "2026-10-14":
        raise SystemExit("FAIL: morning UTC ingest is still the same Shanghai day")

    import io
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "batch.jsonl"
        quiet_out, quiet_err = io.StringIO(), io.StringIO()
        with redirect_stdout(quiet_out), redirect_stderr(quiet_err):
            code = run_ingest(payload, ingested, out, None)
        if code != 0:
            raise SystemExit(f"FAIL: sample --out exit {code}")
        again = Path(tmp) / "batch2.jsonl"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            run_ingest(payload, ingested, again, None)
        if out.read_bytes() != again.read_bytes():
            raise SystemExit("FAIL: --out bytes differ across runs")
        pool = Path(tmp) / "pool"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            run_ingest(payload, ingested, None, pool)
        day_file = pool / "candidates" / "2026-10-14.jsonl"
        if not day_file.is_file():
            raise SystemExit("FAIL: pool day file missing")
        judged = []
        for line in day_file.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["id"] == expected_cid:
                row["status_in_pool"] = "promoted"
                row["archive_id"] = "evt-20261014-fixture-keep"
                row["promotion_path"] = "normal"
                row["notes"] = "alba judgment"
            judged.append(dumps_record(row))
        day_file.write_text("\n".join(judged) + "\n", encoding="utf-8")
        before = day_file.read_text(encoding="utf-8")
        _path, added, kept = merge_pool(pool, first, ingested)
        after = day_file.read_text(encoding="utf-8")
        if added != 0 or kept != len(first) or after != before:
            raise SystemExit(f"FAIL: re-ingest clobbered judgment added={added} kept={kept}")
        promoted = [json.loads(line) for line in after.splitlines() if json.loads(line)["id"] == expected_cid]
        if not promoted or promoted[0]["status_in_pool"] != "promoted" or promoted[0]["notes"] != "alba judgment":
            raise SystemExit("FAIL: judgment fields were not preserved")
        late_rows, _ = records_from_payload(
            {"items": [{"id": "42", "text": "FIXTURE next day"}]},
            late,
        )
        merge_pool(pool, late_rows, late)
        if not (pool / "candidates" / "2026-10-15.jsonl").is_file():
            raise SystemExit("FAIL: Shanghai next-day file was not created")

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise SystemExit("FAIL: jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((ROOT / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for row in first + metrics_rows:
        errors = sorted(validator.iter_errors(row), key=lambda err: list(err.path))
        if errors:
            raise SystemExit(f"FAIL: ingest row schema {errors[0].message}")

    public_out = ROOT / "public" / "_ingest_should_not_write.jsonl"
    try:
        write_batch(public_out, first[:1])
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: ingest wrote under public/")
    if public_out.exists():
        public_out.unlink()
        raise SystemExit("FAIL: public jsonl was created")

    gap_err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(gap_err):
        code = run_ingest(
            {"items": [{"text": "missing"}, {"id": "7", "text": "FIXTURE ok"}]},
            ingested,
            None,
            None,
        )
    if code != 2 or "FETCH_GAP" not in gap_err.getvalue():
        raise SystemExit(f"FAIL: expected exit 2 and FETCH_GAP, got {code}: {gap_err.getvalue()!r}")
    print("OK ingest_x self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write every X fetch item into candidate-pool JSONL.")
    parser.add_argument("--input", "-i", help="Raw fetch JSON file. Default: stdin.")
    parser.add_argument("--out", help="Overwrite this JSONL with the whole batch. For local fixtures and CI.")
    parser.add_argument(
        "--pool-dir",
        help="Pool repo root. Merges into candidates/YYYY-MM-DD.jsonl without overwriting existing ids.",
    )
    parser.add_argument(
        "--ingested-at",
        help="ISO-8601 UTC. Default: payload fetched_at / ingested_at, otherwise the current time.",
    )
    parser.add_argument("--self-check", action="store_true", help="Run deterministic fixture checks.")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not args.out and not args.pool_dir:
        parser.error("pass --out and/or --pool-dir")
    try:
        payload = load_payload(args.input)
        ingested_at = resolve_ingested_at(payload, args.ingested_at)
        return run_ingest(
            payload,
            ingested_at,
            Path(args.out) if args.out else None,
            Path(args.pool_dir) if args.pool_dir else None,
        )
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
