#!/usr/bin/env python3
"""First-report timestamps for event cards.

published_at  original post/publish time (ISO-8601 UTC). Set only from a real
              source clock (X created_at, RSS pubDate, …). Omit when the source
              has no time — do not guess from the display `time` field.
ingested_at   when the card was first written onto the archive board
              (ISO-8601 UTC). Set once on first write; never refresh.

Measured lag = ingested_at − published_at when both are present.
lead_lag_hours / lead_lag_basis stay the assumed-next-digest figure.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UTC = timezone.utc

# Card-level or sources[] keys that are a source publish clock.
# `time` / `date` are Beijing display fields, not a source timestamp.
# `first_seen_at` is when we noticed the source, not when it was published.
SOURCE_TIME_KEYS = ("created_at", "pubDate", "pub_date", "published")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_utc(dt: datetime) -> str | None:
    if dt.tzinfo is None:
        return None
    dt = dt.astimezone(UTC).replace(tzinfo=None)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        frac = f"{dt.microsecond:06d}".rstrip("0")
        return f"{base}.{frac}Z"
    return base + "Z"


def parse_source_timestamp(value) -> str | None:
    """Normalize a source clock to ISO-8601 UTC. Return None if it is not a real time.

    Accepts timezone-aware ISO-8601 (Z or numeric offset), RFC 2822 / RSS
    pubDate, and X `created_at` (`Wed Oct 13 01:56:00 +0000 2026`).
    Naive strings and date-only values are rejected so we do not invent a zone.
    """
    if isinstance(value, datetime):
        return format_utc(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if "T" in s:
        iso = s[:-1] + "+00:00" if s.endswith("Z") else s
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            dt = None
        else:
            return format_utc(dt)
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if dt is None:
        return None
    return format_utc(dt)


def source_timestamp_from_record(record: dict | None) -> str | None:
    """First real publish clock on a card or source object. Does not guess."""
    if not isinstance(record, dict):
        return None
    for key in SOURCE_TIME_KEYS:
        parsed = parse_source_timestamp(record.get(key))
        if parsed:
            return parsed
    for src in record.get("sources") or []:
        if not isinstance(src, dict):
            continue
        for key in SOURCE_TIME_KEYS:
            parsed = parse_source_timestamp(src.get(key))
            if parsed:
                return parsed
    return None


def stamp_first_report(card: dict, *, first_write: bool = False, source_time=None) -> dict:
    """Fill lag timestamps without overwriting and without inventing publish time.

    first_write=True sets ingested_at to now when the key is absent (the card
    is being written onto the archive for the first time). Updates leave an
    existing ingested_at alone, and do not backfill it onto cards already on
    the board — that clock would be the migration time, not the original write.
    """
    if first_write and not str(card.get("ingested_at") or "").strip():
        card["ingested_at"] = utc_now_iso()
    if str(card.get("published_at") or "").strip():
        return card
    parsed = parse_source_timestamp(source_time) if source_time is not None else None
    if parsed is None:
        parsed = source_timestamp_from_record(card)
    if parsed:
        card["published_at"] = parsed
    return card


def measured_lag_hours(card: dict) -> float | None:
    """Hours of ingested_at − published_at, or None when either stamp is missing."""
    pub = parse_source_timestamp(card.get("published_at"))
    ing = parse_source_timestamp(card.get("ingested_at"))
    if not pub or not ing:
        return None
    a = datetime.fromisoformat(pub.replace("Z", "+00:00"))
    b = datetime.fromisoformat(ing.replace("Z", "+00:00"))
    return round((b - a).total_seconds() / 3600, 2)


def self_check() -> None:
    assert parse_source_timestamp("2026-10-13T01:56:00Z") == "2026-10-13T01:56:00Z"
    assert parse_source_timestamp("2026-10-13T09:56:00+08:00") == "2026-10-13T01:56:00Z"
    assert parse_source_timestamp("Wed, 13 Oct 2026 01:56:00 GMT") == "2026-10-13T01:56:00Z"
    assert parse_source_timestamp("Wed Oct 13 01:56:00 +0000 2026") == "2026-10-13T01:56:00Z"
    assert parse_source_timestamp("2026-10-13T01:56:00") is None  # naive
    assert parse_source_timestamp("2026-10-13") is None  # date only
    assert parse_source_timestamp("10-13 01:56") is None  # display clock
    assert parse_source_timestamp(None) is None

    fresh = stamp_first_report(
        {"title": "new"},
        first_write=True,
        source_time="Wed Oct 13 01:56:00 +0000 2026",
    )
    assert fresh["published_at"] == "2026-10-13T01:56:00Z"
    assert fresh["ingested_at"].endswith("Z")

    no_source = stamp_first_report({"title": "bare", "time": "10-13 01:56"}, first_write=True)
    assert "published_at" not in no_source
    assert no_source["ingested_at"].endswith("Z")

    legacy = stamp_first_report({"title": "old", "time": "10-13 01:56"}, first_write=False)
    assert "published_at" not in legacy
    assert "ingested_at" not in legacy

    kept = stamp_first_report(
        {
            "published_at": "2026-10-12T00:00:00Z",
            "ingested_at": "2026-10-12T02:00:00Z",
            "created_at": "Wed Oct 13 01:56:00 +0000 2026",
        },
        first_write=True,
        source_time="2026-10-01T00:00:00Z",
    )
    assert kept["published_at"] == "2026-10-12T00:00:00Z"
    assert kept["ingested_at"] == "2026-10-12T02:00:00Z"
    assert measured_lag_hours(kept) == 2.0
    assert measured_lag_hours({"title": "old"}) is None

    from_rss = stamp_first_report(
        {"sources": [{"pubDate": "Wed, 13 Oct 2026 01:56:00 GMT", "url": "u", "handle": "h", "role": "primary"}]},
        first_write=False,
    )
    assert from_rss["published_at"] == "2026-10-13T01:56:00Z"
    assert "ingested_at" not in from_rss
    print("OK card_times")


if __name__ == "__main__":
    try:
        self_check()
    except AssertionError as exc:
        print(f"FAIL card_times: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
