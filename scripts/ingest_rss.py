#!/usr/bin/env python3
"""Fetch the Phase 4 batch-1 RSS subset into the private candidate pool.

Reads public/config/sources.json and takes every source marked fetch_batch 1.
The baseline six (openai-blog, anthropic-news, deepmind-blog, huggingface-blog,
gh-releases-openai, gh-releases-anthropic-sdk) must stay in batch 1; adding a
source only needs the flag in sources.json, no code change here.
Each source is capped at MAX_PER_SOURCE newest entries so a full-archive feed
cannot flood the pool.

TechCrunch, HN, Reddit, trending, arXiv, Product Hunt, and funding
roundups are fetch_batch 2. This script refuses --batch 2.

Rows match ingest_x: channel=rss, status_in_pool=pending, judgment null.
Same cid / url_norm / --pool-dir merge. Existing ids are not overwritten.
No gate-before-pool: old feed items are still written; annotate_gates
defers them afterwards. This script does not promote and does not call derive.

  python3 scripts/ingest_rss.py --self-check
  python3 scripts/ingest_rss.py --fixture testdata/rss/openai-blog.xml \\
      --source-id openai-blog --out /tmp/rss.jsonl --ingested-at 2026-10-14T12:00:00Z
  python3 scripts/ingest_rss.py --pool-dir ../ai-radar-pool

An empty feed logs 无更新. A source that fails to fetch is a warning;
if every source fails, exit 1. Items with no http(s) link are FETCH_GAP
(exit 2) and the other rows are still written. Refuses to write under public/.

Public CI runs --self-check on fixtures only. The live fetch is the
ingest-rss-pool workflow, which checks out the private pool with
AI_RADAR_POOL_TOKEN.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import parse_source_timestamp, utc_now_iso
    from ingest_x import (
        IngestError,
        assert_not_public,
        candidate_id,
        dumps_record,
        merge_pool,
        normalize_url,
        shanghai_day,
        skeleton,
        write_batch,
    )
else:
    from .card_times import parse_source_timestamp, utc_now_iso
    from .ingest_x import (
        IngestError,
        assert_not_public,
        candidate_id,
        dumps_record,
        merge_pool,
        normalize_url,
        shanghai_day,
        skeleton,
        write_batch,
    )

ROOT = Path(__file__).resolve().parents[1]
UA = "ai-radar-ingest/1.0 (+https://github.com/ruiyaoe-hash/ai-radar)"
SNIPPET_CAP = 2000
TITLE_CAP = 300
MAX_PER_SOURCE = 10
BATCH1_IDS = frozenset(
    {
        "openai-blog",
        "anthropic-news",
        "deepmind-blog",
        "huggingface-blog",
        "gh-releases-openai",
        "gh-releases-anthropic-sdk",
    }
)
DEFERRED_IDS = frozenset(
    {
        "techcrunch-ai",
        "hn-filtered-ai",
        "hn-show-ai",
        "reddit-localllama-hot",
        "hf-trending",
        "gh-trending-python-daily",
        "gh-trending-typescript-daily",
    }
)
WHITESPACE = re.compile(r"\s+")


def local(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def plain_text(value: str) -> str:
    text = WHITESPACE.sub(" ", html.unescape(value or "")).strip()
    return text


def element_plain(el: ET.Element) -> str:
    return plain_text("".join(el.itertext()))


def entry_link(el: ET.Element) -> str | None:
    alt = None
    first = None
    for child in list(el):
        if local(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        text = (child.text or "").strip()
        candidate = href or text
        if not candidate:
            continue
        if first is None:
            first = candidate
        if child.attrib.get("rel", "alternate") == "alternate" and href:
            alt = href
            break
    if alt:
        return alt
    if first:
        return first
    for child in list(el):
        if local(child.tag) == "guid":
            guid = (child.text or "").strip()
            if guid.startswith("http://") or guid.startswith("https://"):
                return guid
    return None


def entry_published(el: ET.Element) -> str | None:
    for name in ("pubDate", "published", "date", "updated"):
        for child in list(el):
            if local(child.tag) != name:
                continue
            parsed = parse_source_timestamp(element_plain(child))
            if parsed:
                return parsed
    return None


def entry_summary(el: ET.Element) -> str | None:
    for name in ("description", "summary", "content"):
        for child in list(el):
            if local(child.tag) != name:
                continue
            text = element_plain(child)
            if not text:
                continue
            if len(text) > SNIPPET_CAP:
                text = text[:SNIPPET_CAP].rstrip()
            return text
    return None


def entry_title(el: ET.Element) -> str | None:
    for child in list(el):
        if local(child.tag) != "title":
            continue
        text = element_plain(child)
        if not text:
            return None
        if len(text) > TITLE_CAP:
            text = text[:TITLE_CAP].rstrip()
        return text
    return None


def parse_feed(blob: bytes) -> list[dict]:
    """RSS 2.0 items and Atom entries. Does not fetch the article body."""
    try:
        root = ET.fromstring(blob)
    except ET.ParseError as exc:
        raise IngestError(f"feed XML: {exc}") from exc
    entries = []
    for el in root.iter():
        if local(el.tag) not in {"item", "entry"}:
            continue
        entries.append(
            {
                "title": entry_title(el),
                "link": entry_link(el),
                "published_at": entry_published(el),
                "summary": entry_summary(el),
            }
        )
    return entries


def entry_to_record(entry: dict, source_id: str, ingested_at: str) -> tuple[dict | None, str | None]:
    link = entry.get("link")
    if not isinstance(link, str) or not link.strip():
        return None, "no_link"
    url_norm = normalize_url(link.strip())
    if not url_norm:
        return None, "unsafe_or_bad_url"
    published = entry.get("published_at")
    if published is not None and not isinstance(published, str):
        published = None
    title = entry.get("title") if isinstance(entry.get("title"), str) else None
    summary = entry.get("summary") if isinstance(entry.get("summary"), str) else None
    record = skeleton(
        candidate_id(f"url:{url_norm}", shanghai_day(published or ingested_at)),
        url_norm,
        ingested_at,
        source_id.strip().lower(),
        published,
        summary,
        title,
        channel="rss",
    )
    return record, None


def select_sources(payload: dict, batch: int = 1) -> list[dict]:
    if batch != 1:
        raise IngestError(
            "only fetch_batch 1 is implemented (T1 lab RSS and GitHub Releases). "
            "Batch 2 (TechCrunch / HN / Reddit / trending) is deferred."
        )
    chosen = []
    for src in payload.get("primary_sources") or []:
        if src.get("fetch_batch") != 1:
            continue
        if src.get("type") not in {"rss", "github_releases"}:
            raise IngestError(f"{src.get('id')}: batch 1 must be rss or github_releases")
        if not isinstance(src.get("url"), str) or not src["url"]:
            raise IngestError(f"{src.get('id')}: missing url")
        chosen.append(src)
    if not chosen:
        raise IngestError("fetch_batch 1 has no rss or github_releases sources")
    missing = BATCH1_IDS - {src["id"] for src in chosen}
    if missing:
        raise IngestError(f"batch 1 lost baseline sources: {sorted(missing)}")
    return chosen


def fetch_bytes(url: str, timeout: int = 20, attempts: int = 3) -> bytes:
    """Live HTTP GET. Self-check must not call this."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(2_000_000)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
    raise IngestError(f"fetch failed: {last}")


def limit_entries(entries: list[dict], max_items: int = MAX_PER_SOURCE) -> list[dict]:
    """Keep the newest max_items entries of one source.

    Some registered feeds are full archives (openai.com/news/rss.xml returns
    over a thousand items). Without this cap the first live run would write the
    whole history into the pool. Feeds are normally newest-first; when every
    entry carries a timestamp we sort explicitly so the cap is deterministic.
    Age is not filtered here: annotate_gates owns the 48h deferral rule.
    """
    if max_items <= 0 or len(entries) <= max_items:
        return entries
    if all(isinstance(entry.get("published_at"), str) for entry in entries):
        entries = sorted(entries, key=lambda entry: entry["published_at"], reverse=True)
    return entries[:max_items]


def ingest_entries(entries: list[dict], source_id: str, ingested_at: str) -> tuple[list[dict], list[str]]:
    records = []
    gaps = []
    for index, entry in enumerate(entries):
        record, reason = entry_to_record(entry, source_id, ingested_at)
        if record is None:
            gaps.append(f"FETCH_GAP source={source_id} index={index} reason={reason or 'no_link'}")
            continue
        records.append(record)
    return records, gaps


def finish_code(n_records: int, n_gaps: int, n_failures: int, n_sources: int) -> int:
    if n_sources and n_failures == n_sources and n_records == 0:
        return 1
    if n_gaps:
        return 2
    return 0


def load_sources(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IngestError(f"sources: {exc}") from exc
    if not isinstance(payload, dict):
        raise IngestError("sources JSON must be an object")
    return payload


def resolve_ingested_at(override: str | None) -> str:
    if not override:
        return utc_now_iso()
    parsed = parse_source_timestamp(override)
    if not parsed:
        raise IngestError(f"--ingested-at is not ISO-8601 UTC: {override!r}")
    return parsed


def run_live(sources: list[dict], ingested_at: str, out: Path | None, pool_dir: Path | None) -> int:
    records: list[dict] = []
    gaps: list[str] = []
    failures: list[str] = []
    for src in sources:
        sid = str(src["id"])
        try:
            blob = fetch_bytes(src["url"])
        except IngestError as exc:
            failures.append(sid)
            print(f"WARN {sid}: {exc}", file=sys.stderr)
            continue
        try:
            entries = parse_feed(blob)
        except IngestError as exc:
            failures.append(sid)
            print(f"WARN {sid}: {exc}", file=sys.stderr)
            continue
        entries = limit_entries(entries)
        made, source_gaps = ingest_entries(entries, sid, ingested_at)
        gaps.extend(source_gaps)
        if not made:
            print(f"无更新 source={sid}")
        records.extend(made)
    return _emit(records, gaps, failures, len(sources), ingested_at, out, pool_dir)


def _emit(records, gaps, failures, n_sources, ingested_at, out, pool_dir) -> int:
    code = finish_code(len(records), len(gaps), len(failures), n_sources)
    if out is not None:
        write_batch(out, records)
        print(f"OK ingest_rss: wrote {len(records)} rows to {out}")
    if pool_dir is not None and records:
        path, added, kept = merge_pool(pool_dir, records, ingested_at)
        if added == 0:
            print("无更新")
        else:
            print(f"OK ingest_rss: pool {path} added={added} kept={kept}")
    elif pool_dir is not None:
        print("无更新")
    elif not records and not gaps and not failures:
        print("无更新")
    for gap in gaps:
        print(gap, file=sys.stderr)
    if code == 2:
        print(f"INGEST incomplete: rows={len(records)} gaps={len(gaps)}", file=sys.stderr)
    if code == 1:
        print("FAIL: every RSS source failed", file=sys.stderr)
    return code


def self_check() -> None:
    """Fixture checks only. Live fetch_bytes is blocked for this call."""
    global fetch_bytes
    real_fetch = fetch_bytes

    def blocked(url: str, timeout: int = 20, attempts: int = 3) -> bytes:
        raise SystemExit(f"FAIL: self-check called live fetch for {url}")

    fetch_bytes = blocked
    try:
        _self_check_body()
    finally:
        fetch_bytes = real_fetch


def _self_check_body() -> None:
    import io
    import json
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout

    sources_path = ROOT / "public" / "config" / "sources.json"
    payload = json.loads(sources_path.read_text(encoding="utf-8"))
    selected = select_sources(payload, 1)
    selected_ids = {src["id"] for src in selected}
    if not BATCH1_IDS <= selected_ids:
        raise SystemExit(f"FAIL: batch 1 missing baseline {sorted(BATCH1_IDS - selected_ids)}")
    for src in payload["primary_sources"]:
        if src["id"] in DEFERRED_IDS and src.get("fetch_batch") != 2:
            raise SystemExit(f"FAIL: {src['id']} should stay batch 2")
        if src["id"] in BATCH1_IDS and src.get("fetch_batch") != 1:
            raise SystemExit(f"FAIL: {src['id']} should be batch 1")
    try:
        select_sources(payload, 2)
    except IngestError as exc:
        if "Batch 2" not in str(exc):
            raise SystemExit(f"FAIL: batch 2 message {exc}")
    else:
        raise SystemExit("FAIL: batch 2 must be refused")

    history = [
        {
            "title": f"t{index}",
            "link": f"https://example.com/{index}",
            "published_at": f"2026-10-{index:02d}T00:00:00Z",
            "summary": None,
        }
        for index in range(1, 16)
    ]
    capped = limit_entries(history)
    if len(capped) != MAX_PER_SOURCE or capped[0]["published_at"] != "2026-10-15T00:00:00Z":
        raise SystemExit(f"FAIL: limit_entries kept {len(capped)} newest={capped[0]['published_at']}")
    if limit_entries(history, 0) != history:
        raise SystemExit("FAIL: limit_entries max 0 must pass through")

    ingested = "2026-10-14T12:00:00Z"
    openai_xml = (ROOT / "testdata" / "rss" / "openai-blog.xml").read_bytes()
    atom_xml = (ROOT / "testdata" / "rss" / "github-release.atom").read_bytes()
    empty_xml = (ROOT / "testdata" / "rss" / "empty.xml").read_bytes()
    openai_entries = parse_feed(openai_xml)
    atom_entries = parse_feed(atom_xml)
    empty_entries = parse_feed(empty_xml)
    if len(openai_entries) != 3 or len(atom_entries) != 1 or empty_entries:
        raise SystemExit(
            f"FAIL: parse counts rss={len(openai_entries)} atom={len(atom_entries)} empty={len(empty_entries)}"
        )
    rows, gaps = ingest_entries(openai_entries, "openai-blog", ingested)
    again, _ = ingest_entries(openai_entries, "openai-blog", ingested)
    if [dumps_record(row) for row in rows] != [dumps_record(row) for row in again]:
        raise SystemExit("FAIL: rss ingest is not deterministic")
    if len(rows) != 2 or len(gaps) != 1 or "reason=no_link" not in gaps[0]:
        raise SystemExit(f"FAIL: expected 2 rows and 1 gap, got {len(rows)} {gaps}")
    today = [row for row in rows if row["url_norm"].endswith("/fixture-rss-today")]
    old = [row for row in rows if row["url_norm"].endswith("/fixture-rss-old")]
    if len(today) != 1 or len(old) != 1:
        raise SystemExit(f"FAIL: fixture urls {[row['url_norm'] for row in rows]}")
    if today[0]["source"]["channel"] != "rss" or today[0]["source"]["handle"] != "openai-blog":
        raise SystemExit("FAIL: rss skeleton channel/handle")
    if today[0]["status_in_pool"] != "pending" or today[0]["prefilter"] is not None:
        raise SystemExit("FAIL: rss ingest must leave judgment empty")
    if today[0]["tier_prior"] is not None or today[0]["source"]["role_guess"] is not None:
        raise SystemExit("FAIL: rss ingest filled a judgment field")
    if "夹具" not in (today[0]["snippet"] or ""):
        raise SystemExit("FAIL: synthetic CJK snippet was dropped")
    if "utm_" in today[0]["url_norm"]:
        raise SystemExit(f"FAIL: tracking query kept {today[0]['url_norm']}")
    expected = candidate_id(f"url:{today[0]['url_norm']}", "20261014")
    if today[0]["id"] != expected:
        raise SystemExit(f"FAIL: cid {today[0]['id']} != {expected}")
    if old[0]["published_at"] != "2026-10-09T01:00:00Z":
        raise SystemExit(f"FAIL: old pubDate {old[0]['published_at']!r}")

    atom_rows, atom_gaps = ingest_entries(atom_entries, "gh-releases-openai", ingested)
    if atom_gaps or "releases/tag/v9.0.0-fixture" not in atom_rows[0]["url_norm"]:
        raise SystemExit(f"FAIL: atom release {atom_rows} {atom_gaps}")
    if atom_rows[0]["title"] != "FIXTURE v9":
        raise SystemExit(f"FAIL: atom title {atom_rows[0]['title']!r}")

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise SystemExit("FAIL: jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((ROOT / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for row in rows + atom_rows:
        errors = sorted(validator.iter_errors(row), key=lambda err: list(err.path))
        if errors:
            raise SystemExit(f"FAIL: rss row schema {errors[0].message}")

    if __package__ in {None, ""}:
        from annotate_gates import annotate_records, options_from_repo
        from ingest_x import parse_utc
    else:
        from .annotate_gates import annotate_records, options_from_repo
        from .ingest_x import parse_utc
    annotated = annotate_records(rows + atom_rows, options_from_repo(parse_utc(ingested)))
    by_url = {row["url_norm"]: row for row in annotated}
    today_g = by_url[today[0]["url_norm"]]
    old_g = by_url[old[0]["url_norm"]]
    atom_g = by_url[atom_rows[0]["url_norm"]]
    if today_g["status_in_pool"] != "active" or today_g["prefilter"] != "PASS" or today_g["tier_prior"] != "T1":
        raise SystemExit(
            f"FAIL: today rss gate {today_g['status_in_pool']} {today_g['prefilter']} {today_g['tier_prior']}"
        )
    if old_g["status_in_pool"] != "deferred" or old_g["drop_reason"] is not None:
        raise SystemExit(f"FAIL: old rss should defer, not drop: {old_g['status_in_pool']} {old_g['drop_reason']}")
    if "rss_backfill_not_today" not in (old_g["notes"] or "") and "stale_window" not in (old_g["notes"] or ""):
        raise SystemExit(f"FAIL: old rss notes {old_g['notes']!r}")
    if atom_g["status_in_pool"] != "active" or atom_g["source"]["role_guess"] != "primary":
        raise SystemExit(f"FAIL: release gate {atom_g['status_in_pool']} {atom_g['source']}")

    quiet_out, quiet_err = io.StringIO(), io.StringIO()
    with redirect_stdout(quiet_out), redirect_stderr(quiet_err):
        code = _emit([], [], [], 1, ingested, None, None)
    if code != 0 or "无更新" not in quiet_out.getvalue():
        raise SystemExit(f"FAIL: empty feed should log 无更新, got {code} {quiet_out.getvalue()!r}")
    if finish_code(0, 0, 2, 2) != 1 or finish_code(1, 1, 0, 1) != 2 or finish_code(1, 0, 0, 1) != 0:
        raise SystemExit("FAIL: finish_code")

    public_out = ROOT / "public" / "_rss_should_not_write.jsonl"
    try:
        write_batch(public_out, rows[:1])
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: rss ingest wrote under public/")
    if public_out.exists():
        public_out.unlink()
        raise SystemExit("FAIL: public jsonl was created")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "batch.jsonl"
        cli_out, cli_err = io.StringIO(), io.StringIO()
        with redirect_stdout(cli_out), redirect_stderr(cli_err):
            code = main(
                [
                    "--fixture",
                    str(ROOT / "testdata" / "rss" / "openai-blog.xml"),
                    "--source-id",
                    "openai-blog",
                    "--ingested-at",
                    ingested,
                    "--out",
                    str(out),
                ]
            )
        if code != 2 or not out.is_file():
            raise SystemExit(f"FAIL: fixture CLI exit {code} stderr {cli_err.getvalue()!r}")
        if "FETCH_GAP" not in cli_err.getvalue():
            raise SystemExit("FAIL: fixture CLI did not log FETCH_GAP")
        pool = Path(tmp) / "pool"
        merge_pool(pool, rows, ingested)
        judged = []
        day = pool / "candidates" / "2026-10-14.jsonl"
        # The old item's Shanghai publish day is 10-09, but the pool file follows ingested_at.
        for line in day.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["id"] == today[0]["id"]:
                row["status_in_pool"] = "promoted"
                row["archive_id"] = "evt-20261014-fixture-keep"
                row["promotion_path"] = "normal"
                row["notes"] = "alba judgment"
            judged.append(dumps_record(row))
        day.write_text("\n".join(judged) + "\n", encoding="utf-8")
        before = day.read_text(encoding="utf-8")
        _path, added, kept = merge_pool(pool, rows, ingested)
        if added != 0 or kept != len(rows) or day.read_text(encoding="utf-8") != before:
            raise SystemExit(f"FAIL: rss re-ingest clobbered judgment added={added} kept={kept}")

    workflow = (ROOT / ".github" / "workflows" / "ingest-rss-pool.yml").read_text(encoding="utf-8")
    review = (ROOT / "docs" / "workflows" / "ingest-rss-pool.yml").read_text(encoding="utf-8")
    if workflow != review:
        raise SystemExit("FAIL: docs/workflows/ingest-rss-pool.yml drifted from .github/workflows")
    for needle in (
        "AI_RADAR_POOL_TOKEN",
        "ruiyaoe-hash/ai-radar-pool",
        "workflow_dispatch",
        "--only-pending",
        "persist-credentials: false",
        "pool_git_push.sh",
        "candidates review",
    ):
        if needle not in workflow:
            raise SystemExit(f"FAIL: workflow missing {needle}")
    push = (ROOT / "scripts" / "pool_git_push.sh").read_text(encoding="utf-8")
    if "pull --rebase" not in push or "无更新" not in push or "git add --" not in push:
        raise SystemExit("FAIL: pool_git_push.sh must rebase, log 无更新, and add explicit paths")
    if "pull_request:" in workflow:
        raise SystemExit("FAIL: RSS ingest must not run on pull_request")
    if "cron:" not in workflow:
        raise SystemExit("FAIL: workflow needs a cron")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    if "ingest_rss.py" in ci or "ingest-rss-pool" in ci:
        raise SystemExit("FAIL: public CI must not live-fetch RSS")
    print("OK ingest_rss self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest batch-1 lab RSS into the private candidate pool.")
    parser.add_argument("--sources", default=str(ROOT / "public" / "config" / "sources.json"))
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--fixture", help="Local RSS or Atom file. No network.")
    parser.add_argument("--source-id", help="sources.json id used with --fixture.")
    parser.add_argument("--out", help="Overwrite this JSONL. Refuses public/.")
    parser.add_argument("--pool-dir", help="Pool repo root. Merges into candidates/YYYY-MM-DD.jsonl.")
    parser.add_argument("--ingested-at", help="ISO-8601 UTC. Default: now.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not args.out and not args.pool_dir:
        parser.error("pass --out and/or --pool-dir")
    try:
        ingested_at = resolve_ingested_at(args.ingested_at)
        if args.fixture:
            source_id = args.source_id or "openai-blog"
            blob = Path(args.fixture).read_bytes()
            entries = parse_feed(blob)
            records, gaps = ingest_entries(entries, source_id, ingested_at)
            if not records and not gaps:
                print(f"无更新 source={source_id}")
            return _emit(records, gaps, [], 1, ingested_at, Path(args.out) if args.out else None, Path(args.pool_dir) if args.pool_dir else None)
        payload = load_sources(Path(args.sources))
        sources = select_sources(payload, args.batch)
        return run_live(
            sources,
            ingested_at,
            Path(args.out) if args.out else None,
            Path(args.pool_dir) if args.pool_dir else None,
        )
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
