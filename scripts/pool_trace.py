#!/usr/bin/env python3
"""Promotion traceability for archive cards.

Public CI never needs the private pool. It always:
  - checks schemas/candidate.schema.json enums
  - replays testdata/ fixtures (synthetic text only)
  - requires candidate_id, or promotion_path=emergency, on archive cards
    whose Beijing date is on or after config.json pool_traceability_since

When a pool snapshot is actually present (AI_RADAR_POOL, POOL_DIR, or a
sibling ../ai-radar-pool with candidates/), in-scope cards must match a
record with status_in_pool=promoted. Emergency cards skip that match.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAND_RE = re.compile(r"^cand-[0-9]{8}-[a-f0-9]{12}$")
FORBIDDEN_DROP_REASONS = ("pending", "wrong_lane", "quota", "quota_defer")
REQUIRED_STATUSES = ("pending", "active", "deferred", "rerouted", "promoted", "dropped")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_since(root: Path | None = None) -> str:
    cfg = json.loads((root or ROOT).joinpath("config.json").read_text(encoding="utf-8"))
    since = cfg.get("pool_traceability_since")
    if not isinstance(since, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", since):
        fail("config.json pool_traceability_since must be YYYY-MM-DD")
    return since


def card_in_scope(card: dict, since: str) -> bool:
    date = card.get("date")
    if not isinstance(date, str) or not date:
        return True
    return date >= since


def reference_errors(cards: list[dict], since: str) -> list[str]:
    """Public-safe check: a new card points at a pool id, or is emergency."""
    errors: list[str] = []
    for card in cards:
        if not card_in_scope(card, since):
            continue
        if card.get("promotion_path") == "emergency":
            continue
        eid = str(card.get("id") or "?")
        cid = card.get("candidate_id")
        if not isinstance(cid, str) or not CAND_RE.match(cid):
            errors.append(
                f"{eid}: archive card dated on/after {since} needs candidate_id "
                "or promotion_path=emergency"
            )
    return errors


def pool_match_errors(cards: list[dict], records: list[dict], since: str) -> list[str]:
    """Snapshot check: non-emergency in-scope cards have a promoted pool row."""
    by_id: dict[str, dict] = {}
    for record in records:
        rid = record.get("id")
        if isinstance(rid, str):
            by_id[rid] = record
    errors: list[str] = []
    for card in cards:
        if not card_in_scope(card, since):
            continue
        if card.get("promotion_path") == "emergency":
            continue
        eid = str(card.get("id") or "?")
        cid = card.get("candidate_id")
        if not isinstance(cid, str):
            errors.append(f"{eid}: no candidate_id to look up in the pool snapshot")
            continue
        record = by_id.get(cid)
        if record is None:
            errors.append(f"{eid}: candidate_id {cid} is not in the pool snapshot")
            continue
        if record.get("status_in_pool") != "promoted":
            errors.append(
                f"{eid}: pool {cid} status_in_pool={record.get('status_in_pool')!r}, expected promoted"
            )
            continue
        if record.get("archive_id") != eid:
            errors.append(
                f"{eid}: pool {cid} archive_id={record.get('archive_id')!r}"
            )
    return errors


def jsonl_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix != ".jsonl":
            fail(f"pool snapshot {path} is not a .jsonl file")
        return [path]
    if not path.is_dir():
        fail(f"pool snapshot {path} does not exist")
    candidates = path / "candidates"
    root = candidates if candidates.is_dir() else path
    return sorted(p for p in root.rglob("*.jsonl") if p.is_file())


def load_pool_records(path: Path) -> list[dict]:
    records: list[dict] = []
    files = jsonl_files(path)
    for fp in files:
        for lineno, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"{fp}:{lineno}: {exc}")
            if not isinstance(record, dict):
                fail(f"{fp}:{lineno}: expected an object")
            records.append(record)
    return records


def load_archive_cards(archive: Path) -> list[dict]:
    cards: list[dict] = []
    if archive.is_file():
        files = [archive]
    else:
        files = sorted(archive.glob("????-??-??.json"))
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("items") or []
        elif isinstance(data, list):
            items = data
        else:
            fail(f"{path}: archive fixture must be a day object or a list")
        for item in items:
            if isinstance(item, dict):
                cards.append(item)
    return cards


def find_pool_snapshot(root: Path | None = None) -> Path | None:
    """A real pool checkout. testdata/ is not a snapshot.

    AI_RADAR_POOL or POOL_DIR must exist when set. An unset variable falls
    through to ../ai-radar-pool only when that directory contains candidates/.
    """
    base = root or ROOT
    for key in ("AI_RADAR_POOL", "POOL_DIR"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (base / path).resolve()
        else:
            path = path.resolve()
        if not path.exists():
            fail(f"{key}={raw} does not exist")
        return path
    sibling = (base.parent / "ai-radar-pool").resolve()
    if sibling != base.resolve() and (sibling / "candidates").is_dir():
        return sibling
    return None


def _validator(root: Path):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((root / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    return schema, Draft202012Validator(schema)


def check_enum_contract(schema: dict) -> None:
    status = schema["properties"]["status_in_pool"]["enum"]
    missing = [name for name in REQUIRED_STATUSES if name not in status]
    if missing:
        fail(f"status_in_pool missing {missing}")
    reasons = schema["properties"]["drop_reason"]["anyOf"][1]["enum"]
    if "no_new_info" not in reasons:
        fail("drop_reason missing no_new_info")
    for banned in FORBIDDEN_DROP_REASONS:
        if banned in reasons:
            fail(f"{banned} must not be a drop_reason")
    if "wrong_lane" in status or "quota" in status or "quota_defer" in status:
        fail("wrong_lane/quota are not pool statuses")


def assert_valid(validator, record: dict, label: str) -> None:
    errors = sorted(validator.iter_errors(record), key=lambda err: list(err.path))
    if errors:
        loc = "/".join(str(part) for part in errors[0].path) or "(root)"
        fail(f"{label}: schema {loc}: {errors[0].message}")


def assert_invalid(validator, record: dict, label: str) -> None:
    if not list(validator.iter_errors(record)):
        fail(f"expected schema rejection: {label}")


def self_check() -> None:
    schema, validator = _validator(ROOT)
    check_enum_contract(schema)
    since = load_since(ROOT)
    if since != "2026-10-15":
        fail(
            "pool_traceability_since moved; legacy archive through 2026-10-14 "
            "has no pool ids. Update testdata and this guard together."
        )

    pool_path = ROOT / "testdata" / "pool"
    records = load_pool_records(pool_path)
    if len(records) < 5:
        fail("testdata/pool fixture is missing synthetic rows")
    for index, record in enumerate(records):
        assert_valid(validator, record, f"testdata pool row {index}")
    reasons = {record.get("drop_reason") for record in records}
    if "no_new_info" not in reasons:
        fail("fixture pool must include a no_new_info drop")
    statuses = {record.get("status_in_pool") for record in records}
    for name in ("pending", "deferred", "rerouted", "promoted", "dropped"):
        if name not in statuses:
            fail(f"fixture pool missing status {name}")
    if any(record.get("drop_reason") for record in records if record.get("status_in_pool") != "dropped"):
        fail("fixture used a drop_reason on a non-drop status")

    try:
        from ingest_x import candidate_id
    except ImportError:
        from scripts.ingest_x import candidate_id

    promoted = next(record for record in records if record["status_in_pool"] == "promoted")
    if promoted["id"] != candidate_id("x-status:9001", "20261015"):
        fail("fixture promoted cid drifted from the status-id hash")

    cards = load_archive_cards(ROOT / "testdata" / "trace")
    ref = reference_errors(cards, since)
    match = pool_match_errors(cards, records, since)
    if ref or match:
        fail("fixture trace should pass: " + "; ".join(ref + match))

    orphan = {
        "id": "evt-20261015-orphan",
        "date": "2026-10-15",
        "promotion_path": "normal",
    }
    if not reference_errors([orphan], since):
        fail("in-scope card without candidate_id must fail")
    emergency = {
        "id": "evt-20261015-emergency-only",
        "date": "2026-10-15",
        "promotion_path": "emergency",
    }
    if reference_errors([emergency], since) or pool_match_errors([emergency], records, since):
        fail("emergency card must not need a pool row")
    old = {"id": "evt-20261014-still-legacy", "date": "2026-10-14"}
    if reference_errors([old], since) or pool_match_errors([old], [], since):
        fail("cards before the cutoff must stay valid without a pool id")

    dropped_id = next(record["id"] for record in records if record["status_in_pool"] == "dropped")
    pointing_at_drop = {
        "id": "evt-20261015-not-promoted",
        "date": "2026-10-15",
        "candidate_id": dropped_id,
    }
    if not pool_match_errors([pointing_at_drop], records, since):
        fail("a dropped pool row must not satisfy promotion")
    missing = {
        "id": "evt-20261015-missing-pool",
        "date": "2026-10-15",
        "candidate_id": "cand-20261015-000000000000",
    }
    if not pool_match_errors([missing], records, since):
        fail("unknown candidate_id must fail when a snapshot is present")

    base = json.loads(json.dumps(promoted))
    for banned in FORBIDDEN_DROP_REASONS:
        bad = json.loads(json.dumps(base))
        bad["status_in_pool"] = "dropped"
        bad["drop_reason"] = banned
        bad["archive_id"] = None
        bad["promotion_path"] = None
        bad["notes"] = "should not validate"
        assert_invalid(validator, bad, banned)
    deferred_with_reason = json.loads(json.dumps(base))
    deferred_with_reason["status_in_pool"] = "deferred"
    deferred_with_reason["drop_reason"] = "no_new_info"
    deferred_with_reason["archive_id"] = None
    assert_invalid(validator, deferred_with_reason, "deferred with drop_reason")
    dropped_without = json.loads(json.dumps(base))
    dropped_without["status_in_pool"] = "dropped"
    dropped_without["drop_reason"] = None
    dropped_without["archive_id"] = None
    assert_invalid(validator, dropped_without, "dropped without drop_reason")
    skip = json.loads(json.dumps(base))
    skip["status_in_pool"] = "dropped"
    skip["drop_reason"] = "editor_skip"
    skip["archive_id"] = None
    skip["promotion_path"] = None
    skip["notes"] = ""
    assert_invalid(validator, skip, "editor_skip without notes")
    skip["notes"] = "fixture note"
    assert_valid(validator, skip, "editor_skip with notes")
    no_new = json.loads(json.dumps(skip))
    no_new["drop_reason"] = "no_new_info"
    assert_valid(validator, no_new, "no_new_info")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "candidates"
        empty.mkdir()
        (empty / ".gitkeep").write_text("", encoding="utf-8")
        if load_pool_records(Path(tmp)) != []:
            fail("an empty candidates/ directory should load as no rows")
        if not pool_match_errors([orphan], [], since):
            fail("an in-scope card must fail against an empty pool snapshot")
    print("OK pool trace self-check")


def live_report() -> None:
    """Run the public reference check, then the snapshot match when a pool exists."""
    since = load_since()
    archive = ROOT / "public" / "archive"
    cards = load_archive_cards(archive)
    ref = reference_errors(cards, since)
    if ref:
        fail("promotion reference: " + "; ".join(ref[:20]))
    in_scope = sum(1 for card in cards if card_in_scope(card, since))
    print(
        f"OK promotion reference: {in_scope} in-scope archive cards "
        f"(Beijing date >= {since}); earlier cards stay legacy"
    )
    snapshot = find_pool_snapshot()
    if snapshot is None:
        print(
            "OK promotion traceability: pool snapshot absent, skipped live match "
            "(public CI does not need the private repo; fixture self-check covers the rule)"
        )
        return
    records = load_pool_records(snapshot)
    match = pool_match_errors(cards, records, since)
    if match:
        fail("promotion traceability: " + "; ".join(match[:20]))
    print(f"OK promotion traceability: live archive vs {snapshot} ({len(records)} pool rows)")


if __name__ == "__main__":
    self_check()
    live_report()
