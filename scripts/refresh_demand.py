#!/usr/bin/env python3
"""Roll atlas bookmark/like counts forward. Does not edit the watchlist.

The public ratio matches scripts/score_pool.py:

    per source: (bookmarks + α) / (likes + β)
    per topic:  (sum of those ratios + prior × n0) / (n + n0)
    prior = α / β, n0 = author_prior_n

Small n stays near the prior. A newer observation on the same URL replaces
the older count. Observations come from atlas.source.json, the previous
public/data/demand.json, archive cards that already carry counts, and
(optionally) private-pool engagement. Only counts are written.

  python3 scripts/refresh_demand.py --self-check
  python3 scripts/refresh_demand.py
  python3 scripts/refresh_demand.py --pool-dir ../ai-radar-pool
  python3 scripts/generate_derived.py

Does not change config.json, practice_handles, or a_tier. Does not copy
post text. Does not add atlas sources.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import read_pool
    from ingest_x import IngestError, normalize_url
    from score_pool import load_score_config, smoothed_bookmark_like
    from shift_ingest_x_to_pool import assert_shift_pool_dir
else:
    from .annotate_gates import read_pool
    from .ingest_x import IngestError, normalize_url
    from .score_pool import load_score_config, smoothed_bookmark_like
    from .shift_ingest_x_to_pool import assert_shift_pool_dir

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SHANGHAI = timezone(timedelta(hours=8))
ORIGIN_RANK = {"atlas": 0, "archive": 1, "pool": 2, "demand": 3}


@dataclass
class Obs:
    likes: int
    bookmarks: int
    views: int | None
    observed_at: str
    origin: str
    stored_from: str


def topic_save_ratio(
    samples: list[tuple[float, float]],
    bookmark_prior: float = 3.0,
    like_prior: float = 5.0,
    author_prior_n: float = 3.0,
) -> float | None:
    """Shrink the mean of per-source smoothed ratios toward α/β when n is small.

    Each sample is (bookmarks, likes). Empty input returns None.
    """
    if not samples:
        return None
    if like_prior <= 0 or author_prior_n <= 0:
        raise IngestError("demand prior is invalid")
    ratios = [
        smoothed_bookmark_like(bookmarks, likes, bookmark_prior, like_prior)
        for bookmarks, likes in samples
    ]
    prior = bookmark_prior / like_prior
    n = float(len(ratios))
    value = (sum(ratios) + prior * author_prior_n) / (n + author_prior_n)
    return round(value, 4)


def _metric(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _pair(obj: dict) -> tuple[int, int, int | None] | None:
    likes = _metric(obj.get("likes"))
    bookmarks = _metric(obj.get("bookmarks"))
    if likes is None and bookmarks is None:
        metrics = obj.get("public_metrics")
        if isinstance(metrics, dict):
            likes = _metric(metrics.get("like_count"))
            if likes is None:
                likes = _metric(metrics.get("likes"))
            bookmarks = _metric(metrics.get("bookmark_count"))
            if bookmarks is None:
                bookmarks = _metric(metrics.get("bookmarks"))
            views = _metric(metrics.get("impression_count"))
            if views is None:
                views = _metric(metrics.get("views"))
            if likes is None and bookmarks is None:
                return None
            return (likes or 0, bookmarks or 0, views)
        return None
    views = _metric(obj.get("views"))
    return (likes or 0, bookmarks or 0, views)


def _pair_from_record(record: dict) -> tuple[int, int, int | None] | None:
    found = _pair(record)
    if found is not None:
        return found
    engagement = record.get("engagement")
    if isinstance(engagement, dict):
        return _pair(engagement)
    return None


def _clock(record: dict, *keys: str) -> str | None:
    engagement = record.get("engagement")
    if isinstance(engagement, dict):
        captured = engagement.get("captured_at")
        if isinstance(captured, str) and len(captured) >= 8:
            return captured
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and len(value) >= 8:
            return value
    return None


def _prefer(new: Obs, old: Obs | None) -> bool:
    if old is None:
        return True
    if new.observed_at != old.observed_at:
        return new.observed_at > old.observed_at
    return ORIGIN_RANK[new.origin] > ORIGIN_RANK[old.origin]


def _urls(record: dict) -> list[str]:
    found: list[str] = []
    raw = record.get("url")
    if isinstance(raw, str) and raw:
        found.append(raw)
    for source in record.get("sources") or []:
        if isinstance(source, dict) and isinstance(source.get("url"), str):
            found.append(source["url"])
    return found


def _stamp(now: datetime) -> tuple[str, str]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc = now.astimezone(timezone.utc).replace(microsecond=0)
    label = now.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M 北京时间")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ"), label


def _whole(value: float) -> int | float:
    if value == int(value):
        return int(value)
    return value


def _formula(bookmark_prior: float, like_prior: float) -> str:
    alpha = int(bookmark_prior) if bookmark_prior == int(bookmark_prior) else bookmark_prior
    beta = int(like_prior) if like_prior == int(like_prior) else like_prior
    return f"(bookmarks+{alpha})/(likes+{beta})，再按样本数向先验收缩"


def build_demand(
    atlas: dict,
    archive_items: list[dict],
    pool_rows: list[dict] | None,
    previous: dict | None,
    *,
    bookmark_prior: float,
    like_prior: float,
    author_prior_n: float,
    now: datetime,
    scanned_archive: bool,
    scanned_pool: bool,
) -> dict:
    """Pick the latest count per atlas source id. Unknown URLs do not become sources."""
    sources = [item for item in (atlas.get("sources") or []) if isinstance(item, dict)]
    known = {str(item.get("id") or "") for item in sources if item.get("id")}
    by_url: dict[str, list[str]] = defaultdict(list)
    chosen: dict[str, Obs] = {}
    snapshot = str(atlas.get("snapshot") or "")
    if len(snapshot) < 8:
        snapshot = "1970-01-01"

    for source in sources:
        sid = str(source.get("id") or "")
        if not sid:
            continue
        norm = normalize_url(str(source.get("url") or ""))
        if norm:
            by_url[norm].append(sid)
        found = _pair_from_record(source)
        if found is None:
            continue
        likes, bookmarks, views = found
        chosen[sid] = Obs(likes, bookmarks, views, snapshot, "atlas", "atlas")

    if isinstance(previous, dict):
        for sid, extra in (previous.get("sources") or {}).items():
            if sid not in known or not isinstance(extra, dict):
                continue
            found = _pair(extra)
            if found is None:
                continue
            observed = extra.get("observed_at")
            if not isinstance(observed, str) or len(observed) < 8:
                continue
            stored = extra.get("from") if extra.get("from") in ORIGIN_RANK else "demand"
            obs = Obs(found[0], found[1], found[2], observed, "demand", stored)
            if _prefer(obs, chosen.get(sid)):
                chosen[sid] = obs

    def _apply(record: dict, origin: str) -> None:
        found = _pair_from_record(record)
        if found is None:
            return
        observed = _clock(record, "published_at", "ingested_at", "date")
        if not observed:
            return
        likes, bookmarks, views = found
        obs = Obs(likes, bookmarks, views, observed, origin, origin)
        seen: set[str] = set()
        for raw in _urls(record):
            norm = normalize_url(raw)
            if not norm:
                continue
            for sid in by_url.get(norm, []):
                if sid in seen:
                    continue
                seen.add(sid)
                if _prefer(obs, chosen.get(sid)):
                    chosen[sid] = obs

    if scanned_archive:
        for item in archive_items:
            if isinstance(item, dict):
                _apply(item, "archive")
    if scanned_pool and pool_rows:
        for row in pool_rows:
            if isinstance(row, dict):
                _apply(row, "pool")

    payload_sources: dict[str, dict] = {}
    for source in sources:
        sid = str(source.get("id") or "")
        obs = chosen.get(sid)
        if obs is None:
            continue
        entry = {
            "likes": obs.likes,
            "bookmarks": obs.bookmarks,
            "observed_at": obs.observed_at,
            "from": obs.stored_from,
        }
        if obs.views is not None:
            entry["views"] = obs.views
        payload_sources[sid] = entry

    inputs = ["atlas"]
    if scanned_archive:
        inputs.append("archive")
    if scanned_pool:
        inputs.append("pool")
    if isinstance(previous, dict) and previous.get("sources"):
        inputs.append("demand")
    refreshed_at, refreshed_label = _stamp(now)
    return {
        "schema_version": 1,
        "refreshed_at": refreshed_at,
        "refreshed_label": refreshed_label,
        "bookmark_prior": _whole(bookmark_prior),
        "like_prior": _whole(like_prior),
        "author_prior_n": _whole(author_prior_n),
        "formula": _formula(bookmark_prior, like_prior),
        "inputs": inputs,
        "pool_counts": bool(scanned_pool),
        "watchlist": "unchanged",
        "sources": payload_sources,
    }


def _dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise IngestError(f"{path}: expected an object")
    return data


def _archive_items(folder: Path) -> list[dict]:
    items: list[dict] = []
    if not folder.is_dir():
        return items
    for path in sorted(folder.glob("????-??-??.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestError(f"{path}: {exc}") from exc
        for item in doc.get("items") or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def refresh_file(
    atlas_path: Path,
    archive_dir: Path,
    demand_path: Path,
    pool_dir: Path | None,
    now: datetime | None = None,
) -> dict:
    atlas = _load_json(atlas_path)
    previous = _load_json(demand_path) if demand_path.is_file() else None
    pool_rows = None
    if pool_dir is not None:
        assert_shift_pool_dir(pool_dir)
        pool_rows = [row for _path, row in read_pool(pool_dir)]
    cfg = load_score_config(ROOT)
    payload = build_demand(
        atlas,
        _archive_items(archive_dir),
        pool_rows,
        previous,
        bookmark_prior=cfg.bookmark_prior,
        like_prior=cfg.like_prior,
        author_prior_n=cfg.author_prior_n,
        now=now or datetime.now(timezone.utc),
        scanned_archive=archive_dir.is_dir(),
        scanned_pool=pool_dir is not None,
    )
    _dump(demand_path, payload)
    return payload


def self_check() -> None:
    """Synthetic counts only. Does not read a private pool or edit config.json."""
    cfg_before = (ROOT / "config.json").read_bytes()
    handles_before = json.loads(cfg_before)["practice_handles"]
    sentinel = "SNIPPET-DO-NOT-COPY-9f3a"
    one = topic_save_ratio([(0, 1)], 3, 5, 3)
    if one != 0.575:
        raise SystemExit(f"FAIL: one small sample should shrink to 0.575, got {one}")
    if one == 0:
        raise SystemExit("FAIL: empty bookmarks must not stay at the raw ratio 0")
    many = topic_save_ratio([(200, 10)] * 8, 3, 5, 3)
    prior = 3 / 5
    if many is None or one is None:
        raise SystemExit("FAIL: ratio missing")
    if abs(one - prior) >= abs(many - prior):
        raise SystemExit(f"FAIL: n=1 ({one}) should sit closer to the prior than n=8 ({many})")
    if topic_save_ratio([], 3, 5, 3) is not None:
        raise SystemExit("FAIL: no samples must not invent a ratio")

    atlas = {
        "snapshot": "2026-10-20",
        "sources": [
            {
                "id": "hw-1",
                "url": "https://x.com/fixturelab/status/2110000000000000001",
                "likes": 10,
                "bookmarks": 1,
                "views": 3,
            },
            {
                "id": "quiet",
                "url": "https://example.com/no-counts",
            },
        ],
    }
    archive = [
        {
            "id": "evt-20261021-fixture",
            "url": "https://twitter.com/fixturelab/status/2110000000000000001",
            "objective": [sentinel],
            "engagement": {
                "likes": 50,
                "bookmarks": 40,
                "captured_at": "2026-10-21T01:00:00Z",
            },
        },
        {
            "id": "evt-old",
            "url": "https://x.com/fixturelab/status/2110000000000000001",
            "likes": 1,
            "bookmarks": 1,
            "published_at": "2026-09-01T00:00:00Z",
        },
        {
            "id": "evt-unmatched",
            "url": "https://example.com/not-in-atlas",
            "likes": 9,
            "bookmarks": 9,
            "published_at": "2026-10-21T00:00:00Z",
            "title": sentinel,
        },
    ]
    pool = [
        {
            "id": "cand-20261021-aabbccddeeff",
            "url": "https://x.com/fixturelab/status/2110000000000000001",
            "snippet": sentinel,
            "engagement": {"likes": 7, "bookmarks": 8, "captured_at": "2026-10-19T00:00:00Z"},
        }
    ]
    rolled = build_demand(
        atlas,
        archive,
        pool,
        None,
        bookmark_prior=3,
        like_prior=5,
        author_prior_n=3,
        now=datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc),
        scanned_archive=True,
        scanned_pool=True,
    )
    blob = json.dumps(rolled, ensure_ascii=False)
    if sentinel in blob:
        raise SystemExit("FAIL: demand roll copied post text")
    if "practice_handles" in blob or "a_tier" in blob:
        raise SystemExit("FAIL: demand roll mentioned the watchlist")
    if rolled["watchlist"] != "unchanged" or rolled["pool_counts"] is not True:
        raise SystemExit(f"FAIL: roll flags {rolled['watchlist']} {rolled['pool_counts']}")
    got = rolled["sources"]["hw-1"]
    if got["bookmarks"] != 40 or got["likes"] != 50 or got["from"] != "archive":
        raise SystemExit(f"FAIL: newer archive count lost: {got}")
    if "quiet" in rolled["sources"] or "evt-unmatched" in rolled["sources"]:
        raise SystemExit("FAIL: roll invented a source")
    if set(rolled["sources"]) - {"hw-1"}:
        raise SystemExit(f"FAIL: unexpected sources {set(rolled['sources'])}")

    kept = build_demand(
        atlas,
        [],
        None,
        {
            "sources": {
                "hw-1": {
                    "likes": 50,
                    "bookmarks": 80,
                    "observed_at": "2026-10-22T00:00:00Z",
                    "from": "pool",
                },
                "ghost": {"likes": 1, "bookmarks": 1, "observed_at": "2026-10-22T00:00:00Z", "from": "pool"},
            }
        },
        bookmark_prior=3,
        like_prior=5,
        author_prior_n=3,
        now=datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc),
        scanned_archive=False,
        scanned_pool=False,
    )
    if kept["sources"]["hw-1"]["bookmarks"] != 80 or kept["sources"]["hw-1"]["from"] != "pool":
        raise SystemExit(f"FAIL: previous roll was overwritten by the snapshot: {kept['sources']['hw-1']}")
    if "ghost" in kept["sources"]:
        raise SystemExit("FAIL: previous roll kept an id that left the atlas")

    tied = build_demand(
        atlas,
        [],
        None,
        {
            "sources": {
                "hw-1": {
                    "likes": 4,
                    "bookmarks": 9,
                    "observed_at": "2026-10-20",
                    "from": "archive",
                }
            }
        },
        bookmark_prior=3,
        like_prior=5,
        author_prior_n=3,
        now=datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc),
        scanned_archive=False,
        scanned_pool=False,
    )
    if tied["sources"]["hw-1"]["bookmarks"] != 9:
        raise SystemExit("FAIL: equal timestamp let the atlas snapshot replace the previous roll")

    if (ROOT / "config.json").read_bytes() != cfg_before:
        raise SystemExit("FAIL: refresh self-check edited config.json")
    if json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["practice_handles"] != handles_before:
        raise SystemExit("FAIL: watchlist changed")
    if "2026-10-21T04:00:00Z" != rolled["refreshed_at"]:
        raise SystemExit(f"FAIL: utc stamp {rolled['refreshed_at']}")
    if rolled["refreshed_label"] != "2026-10-21 12:00 北京时间":
        raise SystemExit(f"FAIL: label {rolled['refreshed_label']}")
    print("OK refresh_demand self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roll atlas demand counts. Watchlist stays put.")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--atlas", type=Path, default=PUBLIC / "data" / "atlas.source.json")
    parser.add_argument("--archive", type=Path, default=PUBLIC / "archive")
    parser.add_argument("--demand", type=Path, default=PUBLIC / "data" / "demand.json")
    parser.add_argument("--pool-dir", type=Path, default=None)
    parser.add_argument("--now", default=None, help="UTC timestamp for the roll, for tests")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    now = None
    if args.now:
        from card_times import parse_source_timestamp

        parsed = parse_source_timestamp(args.now)
        if not parsed:
            raise SystemExit(f"FAIL: --now is not UTC: {args.now}")
        now = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    payload = refresh_file(args.atlas, args.archive, args.demand, args.pool_dir, now)
    where = "私有池计数" if payload["pool_counts"] else "公开字段"
    print(
        f"demand: {len(payload['sources'])} sources, {payload['refreshed_label']}, "
        f"inputs={','.join(payload['inputs'])}, {where}, watchlist unchanged"
    )
    print("下一步: python3 scripts/generate_derived.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
