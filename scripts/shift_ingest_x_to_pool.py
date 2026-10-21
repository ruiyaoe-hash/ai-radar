#!/usr/bin/env python3
"""Alba shift: raw X fetch JSON → private pool, then annotate pending rows.

Does not fetch X, does not promote, and does not write the public archive.
Calls ingest_x, then annotate_gates with --only-pending. Refuses a pool
directory under public/ or anywhere inside the public ai-radar checkout.

  python3 scripts/shift_ingest_x_to_pool.py \\
      --fetch fetch.json --pool-dir ../ai-radar-pool

  python3 scripts/shift_ingest_x_to_pool.py --self-check

Exit 0 when every fetch item became a row and annotate finished.
Exit 2 when some items were FETCH_GAP: identifiable rows are still written
and annotated. Exit 1 on usage, parse, annotate, or path errors.
A later re-run is safe: existing pool ids are not overwritten, and
--only-pending does not rewrite rows that already have a judgment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import options_from_repo, pool_window_start, read_pool, run_paths
    from card_times import utc_now_iso
    from ingest_x import (
        IngestError,
        assert_not_public,
        load_payload,
        parse_utc,
        resolve_ingested_at,
        run_ingest,
    )
else:
    from .annotate_gates import options_from_repo, pool_window_start, read_pool, run_paths
    from .card_times import utc_now_iso
    from .ingest_x import (
        IngestError,
        assert_not_public,
        load_payload,
        parse_utc,
        resolve_ingested_at,
        run_ingest,
    )

ROOT = Path(__file__).resolve().parents[1]


def assert_shift_pool_dir(pool_dir: Path) -> None:
    """Pool JSONL stays in the private checkout, never in this public repo."""
    assert_not_public(pool_dir)
    assert_not_public(pool_dir / "candidates")
    resolved = pool_dir.resolve()
    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise IngestError(
            "refusing to write the candidate pool inside the public ai-radar checkout: "
            f"{pool_dir}. Use a checkout of ruiyaoe-hash/ai-radar-pool "
            "(for example ../ai-radar-pool)."
        )


def annotate_pending(pool_dir: Path, as_of: str | None) -> int:
    """Same path as `annotate_gates.py --pool-dir … --only-pending`."""
    clock = parse_utc(as_of) if as_of else parse_utc(utc_now_iso())
    options = options_from_repo(clock, only_pending=True)
    pairs = read_pool(pool_dir, pool_window_start(clock, options.no_new_info_days))
    records = [row for _path, row in pairs]
    if not records:
        print("无更新")
        return 0
    return run_paths(records, options, None, pairs, pool_dir)


def shift_ingest(
    fetch: Path,
    pool_dir: Path,
    ingested_at: str | None = None,
    as_of: str | None = None,
) -> int:
    """Ingest every fetch item, then annotate rows that are still pending.

    Returns ingest_x's exit code when annotate succeeds (0, or 2 for
    FETCH_GAP). Returns 1 when ingest or annotate fails hard.
    """
    if not fetch.is_file():
        print(f"FAIL: fetch JSON not found: {fetch}", file=sys.stderr)
        return 1
    try:
        assert_shift_pool_dir(pool_dir)
        payload = load_payload(str(fetch))
        ingested = resolve_ingested_at(payload, ingested_at)
        code = run_ingest(payload, ingested, None, pool_dir)
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code
    if code not in (0, 2):
        print(f"FAIL: ingest_x exit {code}", file=sys.stderr)
        return 1
    try:
        annotated = annotate_pending(pool_dir, as_of)
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code
    if annotated != 0:
        print(f"FAIL: annotate_gates exit {annotated}", file=sys.stderr)
        return annotated
    if code == 2:
        print(
            "SHIFT: FETCH_GAP，退出码 2。ingest 已把能识别的行写入；门槛标注已跑完。",
            file=sys.stderr,
        )
    else:
        print("OK shift_ingest_x_to_pool")
    return code


def _fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def self_check() -> None:
    """Fixture checks. Synthetic text only. Does not fetch X."""
    import io
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout

    sample = ROOT / "testdata" / "x-fetch" / "sample.json"
    if not sample.is_file():
        _fail(f"missing {sample}")
    ingested = "2026-10-14T00:05:00Z"
    as_of = "2026-10-14T12:00:00Z"

    with tempfile.TemporaryDirectory() as tmp:
        pool = Path(tmp) / "ai-radar-pool"
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = shift_ingest(sample, pool, ingested, as_of)
        if code != 0:
            _fail(f"sample shift exit {code}: {err.getvalue()}")
        if "OK shift_ingest_x_to_pool" not in out.getvalue():
            _fail(f"missing wrapper ok line: {out.getvalue()!r}")
        day = pool / "candidates" / "2026-10-14.jsonl"
        if not day.is_file():
            _fail("pool day file missing")
        rows = _read_jsonl(day)
        if len(rows) != 4:
            _fail(f"sample wrote {len(rows)} rows, expected 4 (no hand filtering)")
        if any(row.get("prefilter") is None for row in rows):
            _fail("annotate --only-pending left a row without prefilter")
        if any(row.get("source", {}).get("channel") != "x" for row in rows):
            _fail("shift ingest changed channel away from x")
        dupes = [row for row in rows if "official note alpha" in (row.get("snippet") or "")]
        if len(dupes) != 2 or dupes[0]["id"] != dupes[1]["id"]:
            _fail("same status id must share a cid and still emit every row")
        dropped = [row for row in dupes if row.get("drop_reason") == "duplicate_url"]
        kept = [row for row in dupes if row.get("status_in_pool") != "dropped"]
        if len(dropped) != 1 or len(kept) != 1:
            _fail(f"duplicate status should keep one row and drop the other: {dupes}")
        blocked = [row for row in rows if "later gate would block" in (row.get("snippet") or "")]
        if len(blocked) != 1:
            _fail("a future BLOCK item was not written before the gate")
        cjk = [row for row in rows if (row.get("snippet") or "").startswith("夹具")]
        if len(cjk) != 1 or cjk[0].get("prefilter") is None:
            _fail("synthetic CJK snippet was dropped or left unannotated")
        before = day.read_bytes()
        again_out, again_err = io.StringIO(), io.StringIO()
        with redirect_stdout(again_out), redirect_stderr(again_err):
            again = shift_ingest(sample, pool, ingested, as_of)
        if again != 0 or day.read_bytes() != before:
            _fail(f"re-run was not stable exit={again} stderr={again_err.getvalue()!r}")

        judged = _read_jsonl(day)
        target = next(row for row in judged if row["id"] == kept[0]["id"] and row["status_in_pool"] != "dropped")
        target["status_in_pool"] = "promoted"
        target["archive_id"] = "evt-20261014-fixture-keep"
        target["promotion_path"] = "normal"
        target["notes"] = "alba judgment"
        target["prefilter"] = "PASS"
        if not target.get("cluster_id"):
            target["cluster_id"] = "clu-fixturekeep12"
        promoted_id = target["id"]
        # Rewrite only that one object; leave the duplicate drop beside it.
        rewritten = []
        replaced = False
        for row in judged:
            if not replaced and row["id"] == promoted_id and row["status_in_pool"] != "dropped":
                rewritten.append(target)
                replaced = True
            else:
                rewritten.append(row)
        from ingest_x import dumps_record

        day.write_text("".join(dumps_record(row) + "\n" for row in rewritten), encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            held_code = shift_ingest(sample, pool, ingested, as_of)
        if held_code != 0:
            _fail(f"re-run after promotion exit {held_code}")
        held = [row for row in _read_jsonl(day) if row.get("notes") == "alba judgment"]
        if (
            len(held) != 1
            or held[0]["status_in_pool"] != "promoted"
            or held[0]["archive_id"] != "evt-20261014-fixture-keep"
            or held[0]["drop_reason"] is not None
        ):
            _fail(f"--only-pending clobbered a promoted row: {held}")

        other = pool / "candidates" / "2026-10-13.jsonl"
        prior = {
            "schema_version": 1,
            "id": "cand-20261013-abcdefabcdef",
            "url": "https://x.com/examplelab/status/9000",
            "url_norm": "https://x.com/examplelab/status/9000",
            "title": None,
            "snippet": "FIXTURE already judged",
            "published_at": "2026-10-13T01:00:00Z",
            "ingested_at": "2026-10-13T02:00:00Z",
            "source": {"channel": "x", "handle": "examplelab", "role_guess": None},
            "tier_prior": None,
            "participation": None,
            "lane_hint": None,
            "prefilter": "PASS",
            "cluster_id": "clu-priorshift01",
            "status_in_pool": "active",
            "drop_reason": None,
            "archive_id": None,
            "promotion_path": None,
            "notes": "editor hand",
        }
        other.write_text(dumps_record(prior) + "\n", encoding="utf-8")
        prior_bytes = other.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            shift_ingest(sample, pool, ingested, as_of)
        if other.read_bytes() != prior_bytes:
            _fail("only-pending rewrote a day file that had no pending rows")

        gap_fetch = Path(tmp) / "gap.json"
        gap_fetch.write_text(
            json.dumps(
                {
                    "fetched_at": ingested,
                    "items": [
                        {"text": "no identity"},
                        {
                            "id": "42",
                            "text": "FIXTURE kept",
                            "created_at": "2026-10-14T03:00:00Z",
                            "username": "examplelab",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        gap_pool = Path(tmp) / "gap-pool"
        gap_out, gap_err = io.StringIO(), io.StringIO()
        with redirect_stdout(gap_out), redirect_stderr(gap_err):
            gap_code = shift_ingest(gap_fetch, gap_pool, ingested, as_of)
        if gap_code != 2 or "FETCH_GAP" not in gap_err.getvalue():
            _fail(f"expected exit 2 and FETCH_GAP, got {gap_code}: {gap_err.getvalue()!r}")
        if "门槛标注" not in gap_err.getvalue():
            _fail("exit 2 did not report that identifiable rows were annotated")
        gap_rows = _read_jsonl(gap_pool / "candidates" / "2026-10-14.jsonl")
        if len(gap_rows) != 1 or gap_rows[0].get("prefilter") is None:
            _fail(f"FETCH_GAP path did not annotate the kept row: {gap_rows}")
        if gap_rows[0]["url_norm"] != "https://x.com/examplelab/status/42":
            _fail(f"gap row url {gap_rows[0]['url_norm']!r}")

        bad = Path(tmp) / "bad.json"
        bad.write_text("{", encoding="utf-8")
        bad_pool = Path(tmp) / "bad-pool"
        bad_err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(bad_err):
            bad_code = shift_ingest(bad, bad_pool, None, None)
        if bad_code != 1 or bad_pool.exists():
            _fail(f"bad JSON should exit 1 without creating a pool, got {bad_code}")

        missing_err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(missing_err):
            missing = shift_ingest(Path(tmp) / "missing.json", Path(tmp) / "missing-pool", None, None)
        if missing != 1:
            _fail(f"missing fetch should exit 1, got {missing}")

        cli_pool = Path(tmp) / "cli-pool"
        cli_out, cli_err = io.StringIO(), io.StringIO()
        with redirect_stdout(cli_out), redirect_stderr(cli_err):
            cli_code = main(
                ["--fetch", str(sample), "--pool-dir", str(cli_pool), "--ingested-at", ingested, "--as-of", as_of]
            )
        if cli_code != 0 or not (cli_pool / "candidates" / "2026-10-14.jsonl").is_file():
            _fail(f"CLI path exit {cli_code}: {cli_err.getvalue()}")

    for blocked in (ROOT / "public" / "_shift_pool_should_not_exist", ROOT / "_shift_pool_should_not_exist"):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            refused = shift_ingest(sample, blocked, ingested, as_of)
        if refused == 0:
            _fail(f"pool dir was accepted: {blocked}")
        if blocked.exists():
            if blocked.is_dir():
                for child in sorted(blocked.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                blocked.rmdir()
            else:
                blocked.unlink()
            _fail(f"shift helper wrote inside the public repo: {blocked}")
        if "refusing" not in err.getvalue():
            _fail(f"refusal message missing for {blocked}: {err.getvalue()!r}")

    usage_err = io.StringIO()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(usage_err):
            main([])
    except SystemExit as exc:
        if exc.code == 0:
            _fail("missing args should be a usage error")
    else:
        _fail("missing args should exit")
    if "--fetch" not in usage_err.getvalue():
        _fail(f"usage error did not mention --fetch: {usage_err.getvalue()!r}")

    print("OK shift_ingest_x_to_pool self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a raw X fetch into a private pool, then annotate pending rows."
    )
    parser.add_argument("--fetch", help="Raw X fetch JSON file. Not stdin.")
    parser.add_argument(
        "--pool-dir",
        help="Private pool repo root (ruiyaoe-hash/ai-radar-pool). Refuses public/ and this repo.",
    )
    parser.add_argument(
        "--ingested-at",
        help="ISO-8601 UTC. Default: payload fetched_at / ingested_at, otherwise now.",
    )
    parser.add_argument(
        "--as-of",
        help="ISO-8601 UTC clock for annotate_gates stale / backfill checks. Default: now.",
    )
    parser.add_argument("--self-check", action="store_true", help="Run fixture checks. No network.")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not args.fetch or not args.pool_dir:
        parser.error("pass --fetch and --pool-dir")
    return shift_ingest(Path(args.fetch), Path(args.pool_dir), args.ingested_at, args.as_of)


if __name__ == "__main__":
    sys.exit(main())
