#!/usr/bin/env python3
"""L0 annotate gates（门槛标注）and L2 clustering（轻量聚簇）.

Pipeline order stays: ingest all → annotate gates → cluster → score → promote.
This script runs the gates, then clustering, then the 7-day no_new_info check
that needs a cluster_id. It does not score, rank, or write public cards.

Rows are already in the pool. BLOCK / UNKNOWN stay as rows. Deferred and
rerouted are statuses, not drop reasons. no_new_info is a true drop.
wrong_lane, quota, and quota_defer are never written.

Defaults, on purpose:
  - no reliable clock → prefilter UNKNOWN and status pending (not a silent skip).
    --no-time-policy drop is the only path to drop_reason no_reliable_time.
  - age > 48h → status deferred, drop_reason null (not today's slot).
    --stale-policy drop is the only path to drop_reason stale_old.
  - RSS whose Shanghai publish date is before --as-of → deferred
    (rss backfill is not today). That is not stale_old.
  - role=report with no primary/official link → stays active, with a note that
    formal P0 is blocked. drop_reason media_alone only when the input notes
    contain attempt_formal_p0.
  - a handle or domain missing from the tier map is not hard-excluded.

Promoted, rerouted, editor_skip, and low_score rows keep their status. cluster_id is
filled when it was empty. Same-cluster rows that are already promoted get a
correction_path note on the other rows. This phase does not write a new card.

  python3 scripts/annotate_gates.py --self-check
  python3 scripts/annotate_gates.py --input rows.jsonl --out /tmp/out.jsonl \\
      --as-of 2026-10-14T12:00:00Z
  python3 scripts/annotate_gates.py --pool-dir ../ai-radar-pool --only-pending

Refuses to write under public/.
Public title / objective / so_what prose is written on the archive card, not here.
See scripts/human_layer.py and docs/AIHOT对接与表达规范-v0.md.
Gate outcomes (including media_alone) are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from card_times import parse_source_timestamp
    from generate_derived import safe_http_url
    from ingest_x import (
        SHANGHAI,
        IngestError,
        assert_not_public,
        dumps_record,
        merge_pool,
        normalize_url,
        parse_utc,
        write_batch,
    )
else:
    from .card_times import parse_source_timestamp
    from .generate_derived import safe_http_url
    from .ingest_x import (
        SHANGHAI,
        IngestError,
        assert_not_public,
        dumps_record,
        merge_pool,
        normalize_url,
        parse_utc,
        write_batch,
    )

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"primary", "analysis", "report"}
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
# Words for ASCII. CJK is character bigrams inside each run, not the whole run:
# a comma used to turn one near-copy into several brand-new "words", and a
# one-character title edit made Jaccard zero.
ASCII_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
AI_RE = re.compile(
    r"\b(?:ai|llm|llms|gpt|chatgpt|claude|gemini|openai|anthropic|huggingface|"
    r"transformer|neural|agents?|machine learning)\b|模型|大模型|智能体",
    re.I,
)
NON_AI_RE = re.compile(
    r"\b(?:premier league|weather forecast|celebrity wedding|recipe for)\b",
    re.I,
)
STATUS_URL_RE = re.compile(r"/status/\d+")


@dataclass
class GateOptions:
    as_of: datetime
    stale_hours: float = 48
    stale_policy: str = "defer"
    no_time_policy: str = "pending"
    same_source_window_minutes: int = 30
    no_new_info_days: int = 7
    novel_token_min: int = 3
    title_threshold: float = 0.72
    title_similarity: bool = True
    only_pending: bool = False
    handles: dict[str, dict] = field(default_factory=dict)
    domains: list[dict] = field(default_factory=list)
    entity_rules: list[dict] = field(default_factory=list)
    a_tier: set[str] = field(default_factory=set)
    practice_handles: set[str] = field(default_factory=set)

    def validate(self) -> None:
        if self.stale_policy not in {"defer", "drop"}:
            raise IngestError("--stale-policy must be defer or drop")
        if self.no_time_policy not in {"pending", "drop"}:
            raise IngestError("--no-time-policy must be pending or drop")
        if self.as_of.tzinfo is None:
            raise IngestError("--as-of needs a timezone")


def load_tier_map(path: Path) -> tuple[dict[str, dict], list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    handles: dict[str, dict] = {}
    for entry in data.get("handles") or []:
        match = str(entry.get("match") or "").strip().lower()
        _check_entry(entry, f"handle {match}")
        if not match:
            raise IngestError(f"{path}: handle match is empty")
        handles[match] = entry
    domains = []
    for entry in data.get("domains") or []:
        _check_entry(entry, f"domain {entry.get('domain')}")
        if not entry.get("domain"):
            raise IngestError(f"{path}: domain is empty")
        domains.append(entry)
    return handles, domains


def load_entity_rules(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    compiled = []
    for rule in data.get("rules") or []:
        try:
            pattern = re.compile(rule["pattern"], re.I)
        except re.error as exc:
            raise IngestError(f"{path}: bad pattern {rule.get('id')}: {exc}") from exc
        compiled.append(
            {
                "id": rule["id"],
                "kind": rule.get("kind") or "entity",
                "cluster_alone": bool(rule.get("cluster_alone")),
                "pattern": pattern,
            }
        )
    return compiled


def load_config_handles(path: Path) -> tuple[set[str], set[str]]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    a_tier = {str(h).strip().lower() for h in cfg.get("a_tier") or [] if str(h).strip()}
    practice = {str(h).strip().lower() for h in cfg.get("practice_handles") or [] if str(h).strip()}
    return a_tier, practice


def options_from_repo(as_of: datetime, root: Path | None = None, **overrides) -> GateOptions:
    root = root or ROOT
    handles, domains = load_tier_map(root / "config" / "source_tier_map.json")
    rules = load_entity_rules(root / "config" / "entity_rules.json")
    a_tier, practice = load_config_handles(root / "config.json")
    opts = GateOptions(
        as_of=as_of,
        handles=handles,
        domains=domains,
        entity_rules=rules,
        a_tier=a_tier,
        practice_handles=practice,
    )
    for key, value in overrides.items():
        setattr(opts, key, value)
    opts.validate()
    return opts


def _check_entry(entry: dict, label: str) -> None:
    role = entry.get("role_guess")
    if role not in ROLES:
        raise IngestError(f"{label}: role_guess must be primary, analysis, or report")
    gate = entry.get("gate")
    if gate != _expected_gate(entry):
        raise IngestError(
            f"{label}: gate {gate!r} does not match tier/role "
            f"(expected {_expected_gate(entry)})"
        )


def _expected_gate(entry: dict) -> str:
    if entry.get("role_guess") == "report" or entry.get("tier_prior") == "T3":
        return "high"
    if entry.get("tier_prior") in {"T1", "a_tier"} or entry.get("role_guess") == "primary":
        return "low"
    return "open"


def canonical_url(url: object) -> str | None:
    if not isinstance(url, str) or not safe_http_url(url):
        return None
    return normalize_url(url)


def is_status_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in {"x.com", "twitter.com"}:
        return False
    return bool(STATUS_URL_RE.search(parts.path or ""))


def extract_http_urls(text: str) -> list[str]:
    found = []
    for raw in URL_RE.findall(text or ""):
        cleaned = raw.rstrip(".,);:]}>\"'")
        if cleaned:
            found.append(cleaned)
    return found


def evidence_links(row: dict) -> set[str]:
    """Outbound http(s) links in title/snippet, excluding this row's own URL."""
    blob = " ".join(part for part in (row.get("title"), row.get("snippet")) if isinstance(part, str))
    own = canonical_url(row.get("url_norm") or row.get("url"))
    found: set[str] = set()
    for raw in extract_http_urls(blob):
        norm = canonical_url(raw)
        if not norm or is_status_url(norm) or norm == own:
            continue
        found.add(norm)
    return found


def cluster_links(row: dict) -> set[str]:
    """Links that may join a cluster. X status permalinks are not keys."""
    links = set(evidence_links(row))
    own = canonical_url(row.get("url_norm") or row.get("url"))
    if own and not is_status_url(own):
        links.add(own)
    return links


def text_tokens(text: str) -> set[str]:
    """ASCII words plus CJK character bigrams. Single CJK characters are not tokens."""
    if not text:
        return set()
    lowered = text.lower()
    tokens = set(ASCII_TOKEN_RE.findall(lowered))
    for run in CJK_RUN_RE.findall(lowered):
        if len(run) < 2:
            continue
        tokens.update(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def content_tokens(row: dict) -> set[str]:
    blob = " ".join(part for part in (row.get("title"), row.get("snippet")) if isinstance(part, str))
    blob = URL_RE.sub(" ", blob)
    return text_tokens(blob)


def title_tokens(title: object) -> set[str]:
    if not isinstance(title, str) or not title.strip():
        return set()
    return text_tokens(title)


def jaccard(left: set[str], right: set[str]) -> float:
    """Empty titles are not similar. A missing X title must not glue a cluster together."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def is_substantive(row: dict, anchors: list[dict], min_novel: int) -> bool:
    """True when row adds an outbound link or enough new tokens vs anchors."""
    if not anchors:
        return True
    old_links: set[str] = set()
    old_tokens: set[str] = set()
    for anchor in anchors:
        old_links |= evidence_links(anchor)
        old_tokens |= content_tokens(anchor)
    if evidence_links(row) - old_links:
        return True
    return len(content_tokens(row) - old_tokens) >= min_novel


def row_clock(value) -> datetime | None:
    parsed = parse_source_timestamp(value)
    if not parsed:
        return None
    return datetime.fromisoformat(parsed.replace("Z", "+00:00"))


def sort_key(row: dict) -> tuple:
    published = row.get("published_at") or ""
    ingested = row.get("ingested_at") or ""
    return (published or ingested, ingested, row.get("id") or "")


def source_key(row: dict) -> str | None:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    handle = source.get("handle")
    channel = source.get("channel") or "?"
    if not isinstance(handle, str) or not handle.strip():
        return None
    return f"{channel}:{handle.strip().lower()}"


def lookup_domain(url: str, domains: list[dict]) -> dict | None:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host:
        return None
    path = parts.path or "/"
    best = None
    best_score = -1
    for entry in domains:
        domain = str(entry["domain"]).lower()
        if host != domain and not host.endswith("." + domain):
            continue
        prefix = entry.get("path_prefix")
        if prefix and not path.lower().startswith(str(prefix).lower()):
            continue
        score = len(domain) * 10 + len(prefix or "")
        if score > best_score:
            best = entry
            best_score = score
    return best


def url_is_primary(url: str, options: GateOptions) -> bool:
    if is_status_url(url):
        parts = urllib.parse.urlsplit(url)
        segs = [part for part in parts.path.split("/") if part]
        handle = segs[0].lower() if segs else ""
        if handle in {"i"}:
            return False
        entry = options.handles.get(handle)
        return bool(entry and entry.get("role_guess") == "primary")
    found = lookup_domain(url, options.domains)
    return bool(found and found.get("role_guess") == "primary")


def apply_trust(row: dict, options: GateOptions) -> str:
    """Fill tier_prior and role_guess. Return low / high / open. Unlisted stays eligible."""
    source = row.setdefault("source", {"channel": "web", "handle": None, "role_guess": None})
    handle = source.get("handle")
    handle_l = handle.strip().lower() if isinstance(handle, str) else ""
    handle_rule = options.handles.get(handle_l)
    if handle_l and handle_l in options.practice_handles:
        row["tier_prior"] = "practice"
        source["role_guess"] = handle_rule.get("role_guess") if handle_rule else None
        return "low"
    if handle_l and handle_l in options.a_tier:
        row["tier_prior"] = "a_tier"
        source["role_guess"] = handle_rule.get("role_guess") if handle_rule else None
        return "low"
    if handle_rule:
        row["tier_prior"] = handle_rule.get("tier_prior")
        source["role_guess"] = handle_rule.get("role_guess")
        return _expected_gate(handle_rule)
    own = canonical_url(row.get("url_norm") or row.get("url"))
    found = lookup_domain(own, options.domains) if own else None
    if found:
        row["tier_prior"] = found.get("tier_prior")
        source["role_guess"] = found.get("role_guess")
        return _expected_gate(found)
    row["tier_prior"] = None
    source["role_guess"] = None
    return "open"


def prefilter_of(row: dict, gate: str) -> str:
    text = " ".join(part for part in (row.get("title"), row.get("snippet")) if isinstance(part, str)).strip()
    if text and NON_AI_RE.search(text) and not AI_RE.search(text):
        return "BLOCK"
    if not text:
        return "PASS" if gate == "low" else "UNKNOWN"
    return "PASS"


def has_primary_ref(row: dict, options: GateOptions) -> bool:
    own = canonical_url(row.get("url_norm") or row.get("url"))
    if own and url_is_primary(own, options):
        return True
    return any(url_is_primary(link, options) for link in evidence_links(row))


def is_media_alone(row: dict, options: GateOptions) -> bool:
    role = (row.get("source") or {}).get("role_guess")
    return role == "report" and not has_primary_ref(row, options)


def user_prefix(notes: str) -> str:
    text = (notes or "").strip()
    if not text or text.startswith("gate:"):
        return ""
    if " gate:" in text:
        return text.split(" gate:", 1)[0].strip()
    return text


def compose_notes(original: str, bits: list[str]) -> str:
    parts = []
    prefix = user_prefix(original)
    if prefix:
        parts.append(prefix)
    parts.extend(bits)
    return " ".join(parts).strip()


def is_locked(row: dict, only_pending: bool) -> bool:
    if row.get("status_in_pool") in {"promoted", "rerouted"}:
        return True
    if row.get("drop_reason") in {"editor_skip", "low_score"}:
        return True
    if only_pending and not (row.get("status_in_pool") == "pending" and row.get("prefilter") is None):
        return True
    return False


class _UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, idx: int) -> int:
        while self.parent[idx] != idx:
            self.parent[idx] = self.parent[self.parent[idx]]
            idx = self.parent[idx]
        return idx

    def union(self, left: int, right: int) -> None:
        ra, rb = self.find(left), self.find(right)
        if ra == rb:
            return
        if ra > rb:
            ra, rb = rb, ra
        self.parent[rb] = ra


def entity_matches(row: dict, rules: list[dict]) -> list[tuple[str, bool]]:
    text = " ".join(part for part in (row.get("title"), row.get("snippet")) if isinstance(part, str))
    found: list[tuple[str, bool]] = []
    for rule in rules:
        if rule["cluster_alone"]:
            for match in rule["pattern"].finditer(text):
                span = match.group(0)
                span = span.upper() if rule["kind"] == "cve" else span.lower()
                found.append((f"{rule['id']}:{span}", True))
        elif rule["pattern"].search(text):
            found.append((rule["id"], False))
    return found


def compute_cluster_ids(rows: list[dict], options: GateOptions, locked: list[bool]) -> list[str]:
    """Shared links, then entity rules. Title similarity never unions by itself."""
    size = len(rows)
    uf = _UnionFind(size)
    link_of = [cluster_links(row) for row in rows]
    by_link: dict[str, list[int]] = defaultdict(list)
    for idx, links in enumerate(link_of):
        for link in links:
            by_link[link].append(idx)
    for idxs in by_link.values():
        for other in idxs[1:]:
            uf.union(idxs[0], other)

    matched = [entity_matches(row, options.entity_rules) for row in rows]
    alone: dict[str, list[int]] = defaultdict(list)
    soft: dict[str, list[int]] = defaultdict(list)
    for idx, pairs in enumerate(matched):
        for key, is_alone in pairs:
            if is_alone:
                alone[key].append(idx)
            else:
                soft[key].append(idx)
    for idxs in alone.values():
        for other in idxs[1:]:
            uf.union(idxs[0], other)
    if options.title_similarity:
        titles = [title_tokens(row.get("title")) for row in rows]
        for idxs in soft.values():
            for pos, left in enumerate(idxs):
                for right in idxs[pos + 1 :]:
                    if jaccard(titles[left], titles[right]) >= options.title_threshold:
                        uf.union(left, right)

    members: dict[int, list[int]] = defaultdict(list)
    for idx in range(size):
        members[uf.find(idx)].append(idx)

    assigned = [""] * size
    for group in members.values():
        locked_ids = [
            rows[idx].get("cluster_id")
            for idx in group
            if locked[idx] and isinstance(rows[idx].get("cluster_id"), str) and rows[idx].get("cluster_id")
        ]
        if locked_ids:
            cid = min(locked_ids)
        else:
            links = sorted({link for idx in group for link in link_of[idx]})
            ents = sorted({key for idx in group for key, is_alone in matched[idx] if is_alone})
            if links:
                canonical = "link:" + links[0]
            elif ents:
                canonical = "entity:" + ents[0]
            else:
                canonical = "id:" + min(str(rows[idx].get("id") or idx) for idx in group)
            cid = "clu-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        for idx in group:
            assigned[idx] = cid
    return assigned


def _set_decision(row: dict, status: str, reason: str | None, prefilter: str, original_notes: str, bits: list[str]) -> None:
    row["status_in_pool"] = status
    row["drop_reason"] = reason
    row["prefilter"] = prefilter
    row["notes"] = compose_notes(original_notes, bits)
    if status != "promoted":
        # Gates never promote. Leave an existing archive pointer untouched only on locked rows.
        pass


def annotate_records(records: list[dict], options: GateOptions) -> list[dict]:
    """Return new row dicts. Does not mutate the input list's dicts."""
    options.validate()
    rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in records]
    locked = [is_locked(row, options.only_pending) for row in rows]
    order = sorted(range(len(rows)), key=lambda idx: sort_key(rows[idx]))
    seen_ids: dict[str, int] = {}
    seen_urls: dict[str, int] = {}
    window = timedelta(minutes=options.same_source_window_minutes)
    # Same-source anchors that were not themselves duplicate drops.
    anchors: list[tuple[datetime, str, dict]] = []

    for idx in order:
        row = rows[idx]
        original_notes = row.get("notes") or ""
        if not isinstance(row.get("source"), dict):
            raise IngestError(f"{row.get('id')}: source must be an object")
        if locked[idx]:
            canon = canonical_url(row.get("url_norm") or row.get("url"))
            if canon:
                row["url_norm"] = canon
                seen_urls.setdefault(canon, idx)
            if isinstance(row.get("id"), str):
                seen_ids.setdefault(row["id"], idx)
            clock = row_clock(row.get("published_at"))
            key = source_key(row)
            if clock and key and row.get("status_in_pool") != "dropped":
                anchors.append((clock, key, row))
            continue

        canon = canonical_url(row.get("url_norm") or row.get("url"))
        if canon:
            row["url_norm"] = canon
        gate = apply_trust(row, options)
        prefilter = prefilter_of(row, gate)
        attempt_p0 = "attempt_formal_p0" in original_notes
        rid = row.get("id")

        if canon is None or prefilter == "BLOCK":
            _set_decision(
                row,
                "dropped",
                "prefilter_block",
                "BLOCK",
                original_notes,
                ["gate: prefilter_block unsafe_url" if canon is None else "gate: prefilter_block"],
            )
            if isinstance(rid, str):
                seen_ids.setdefault(rid, idx)
            if canon:
                seen_urls.setdefault(canon, idx)
            continue

        if isinstance(rid, str) and rid in seen_ids:
            _set_decision(row, "dropped", "duplicate_url", prefilter, original_notes, ["gate: duplicate_url seen_id"])
            continue
        if canon in seen_urls:
            _set_decision(row, "dropped", "duplicate_url", prefilter, original_notes, ["gate: duplicate_url"])
            if isinstance(rid, str):
                seen_ids.setdefault(rid, idx)
            continue

        clock = row_clock(row.get("published_at"))
        key = source_key(row)
        if clock and key:
            window_rows = [item for when, src, item in anchors if src == key and abs(clock - when) <= window]
            if window_rows and not is_substantive(row, window_rows, options.novel_token_min):
                _set_decision(
                    row,
                    "dropped",
                    "duplicate_event",
                    prefilter,
                    original_notes,
                    ["gate: duplicate_event same_source_window"],
                )
                if isinstance(rid, str):
                    seen_ids.setdefault(rid, idx)
                seen_urls.setdefault(canon, idx)
                continue

        if clock is None:
            if options.no_time_policy == "drop":
                _set_decision(
                    row,
                    "dropped",
                    "no_reliable_time",
                    "UNKNOWN",
                    original_notes,
                    ["gate: no_reliable_time drop"],
                )
            else:
                _set_decision(
                    row,
                    "pending",
                    None,
                    "UNKNOWN",
                    original_notes,
                    ["gate: no_reliable_time pending"],
                )
            if isinstance(rid, str):
                seen_ids.setdefault(rid, idx)
            seen_urls.setdefault(canon, idx)
            continue

        age = options.as_of - clock
        stale = age > timedelta(hours=options.stale_hours)
        backfill = False
        channel = (row.get("source") or {}).get("channel")
        if channel == "rss":
            backfill = clock.astimezone(SHANGHAI).date() < options.as_of.astimezone(SHANGHAI).date()
        if stale and options.stale_policy == "drop":
            _set_decision(row, "dropped", "stale_old", prefilter, original_notes, ["gate: stale_old"])
        elif stale or backfill:
            reasons = []
            if stale:
                reasons.append(f"stale_window>{options.stale_hours:g}h")
            if backfill:
                reasons.append("rss_backfill_not_today")
            _set_decision(
                row,
                "deferred",
                None,
                prefilter,
                original_notes,
                ["gate: deferred " + " ".join(reasons)],
            )
        elif is_media_alone(row, options) and attempt_p0:
            _set_decision(
                row,
                "dropped",
                "media_alone",
                prefilter,
                original_notes,
                ["gate: media_alone drop (attempt_formal_p0)"],
            )
        elif is_media_alone(row, options):
            _set_decision(
                row,
                "active",
                None,
                prefilter,
                original_notes,
                ["gate: media_alone blocks formal P0 (P0-待证 or P1)"],
            )
        else:
            _set_decision(row, "active", None, prefilter, original_notes, [])

        if isinstance(rid, str):
            seen_ids.setdefault(rid, idx)
        seen_urls.setdefault(canon, idx)
        if clock and key and row.get("status_in_pool") != "dropped":
            anchors.append((clock, key, row))

    original_clusters = [row.get("cluster_id") for row in rows]
    computed = compute_cluster_ids(rows, options, locked)
    for idx, cid in enumerate(computed):
        if locked[idx] and original_clusters[idx]:
            rows[idx]["cluster_id"] = original_clusters[idx]
        else:
            rows[idx]["cluster_id"] = cid

    _apply_no_new_info(rows, locked, options)
    _apply_correction_notes(rows, locked)
    return rows


def _apply_no_new_info(rows: list[dict], locked: list[bool], options: GateOptions) -> None:
    grouped: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        cid = row.get("cluster_id")
        if isinstance(cid, str):
            grouped[cid].append(idx)
    limit = timedelta(days=options.no_new_info_days)
    for idxs in grouped.values():
        idxs.sort(key=lambda idx: sort_key(rows[idx]))
        kept: list[tuple[dict, datetime | None]] = []
        for idx in idxs:
            row = rows[idx]
            if row.get("status_in_pool") == "dropped":
                continue
            clock = row_clock(row.get("published_at")) or row_clock(row.get("ingested_at"))
            if locked[idx] or row.get("status_in_pool") != "active" or clock is None:
                kept.append((row, clock))
                continue
            in_window = [anchor for anchor, when in kept if when is not None and abs(clock - when) <= limit]
            if in_window and not is_substantive(row, in_window, options.novel_token_min):
                row["status_in_pool"] = "dropped"
                row["drop_reason"] = "no_new_info"
                bit = "gate: no_new_info"
                if bit not in (row.get("notes") or ""):
                    row["notes"] = ((row.get("notes") or "") + " " + bit).strip()
                continue
            kept.append((row, clock))


def _apply_correction_notes(rows: list[dict], locked: list[bool]) -> None:
    grouped: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        cid = row.get("cluster_id")
        if isinstance(cid, str):
            grouped[cid].append(idx)
    for idxs in grouped.values():
        promoted = [
            rows[idx]
            for idx in idxs
            if rows[idx].get("status_in_pool") == "promoted" or rows[idx].get("archive_id")
        ]
        if not promoted:
            continue
        ref = promoted[0].get("archive_id") or promoted[0].get("id")
        note = f"gate: correction_path update {ref} instead of a new card"
        for idx in idxs:
            row = rows[idx]
            if locked[idx] or row.get("status_in_pool") in {"promoted", "dropped"}:
                continue
            if "correction_path" in (row.get("notes") or ""):
                continue
            row["notes"] = ((row.get("notes") or "") + " " + note).strip()


def load_records(raw: str) -> list[dict]:
    text = raw.strip()
    if not text:
        return []
    if text[0] in "[{":
        payload = json.loads(text)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
            rows = payload["records"]
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            raise IngestError("JSON must be a record, a list, or {records: []}")
        if not all(isinstance(row, dict) for row in rows):
            raise IngestError("each candidate row must be an object")
        return rows
    rows = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestError(f"jsonl line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise IngestError(f"jsonl line {line_no}: expected an object")
        rows.append(row)
    return rows


def read_pool(pool_dir: Path) -> list[tuple[Path, dict]]:
    assert_not_public(pool_dir)
    folder = pool_dir / "candidates"
    if not folder.is_dir():
        return []
    pairs: list[tuple[Path, dict]] = []
    for path in sorted(folder.glob("*.jsonl")):
        assert_not_public(path)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IngestError(f"{path} line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise IngestError(f"{path} line {line_no}: expected an object")
            pairs.append((path, row))
    return pairs


def write_pool(pool_dir: Path, pairs: list[tuple[Path, dict]], rows: list[dict]) -> None:
    assert_not_public(pool_dir)
    by_path: dict[Path, list[dict]] = defaultdict(list)
    for (path, _old), row in zip(pairs, rows):
        by_path[path].append(row)
    for path, group in by_path.items():
        assert_not_public(path)
        body = "".join(dumps_record(row) + "\n" for row in group)
        path.write_text(body, encoding="utf-8")


def summarize(rows: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("status_in_pool"))] += 1
    return (
        f"rows={len(rows)} active={counts['active']} pending={counts['pending']} "
        f"deferred={counts['deferred']} dropped={counts['dropped']} "
        f"promoted={counts['promoted']} rerouted={counts['rerouted']}"
    )


def run_paths(records: list[dict], options: GateOptions, out: Path | None, pool_pairs, pool_dir: Path | None) -> int:
    annotated = annotate_records(records, options)
    if out is not None:
        write_batch(out, annotated)
        print(f"OK annotate_gates: wrote {out}")
    if pool_dir is not None and pool_pairs is not None:
        write_pool(pool_dir, pool_pairs, annotated)
        print(f"OK annotate_gates: pool {pool_dir}")
    print(f"OK annotate_gates: {summarize(annotated)} as_of={options.as_of.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    return 0


def _expand_fixture_row(raw: dict) -> dict:
    url = raw["url"]
    norm = canonical_url(url) or url
    published = raw["published_at"] if "published_at" in raw else "2026-10-14T10:00:00Z"
    return {
        "schema_version": 1,
        "id": raw["id"],
        "url": norm if canonical_url(url) else url,
        "url_norm": norm,
        "title": raw["title"] if "title" in raw else None,
        "snippet": raw.get("snippet"),
        "published_at": published,
        "ingested_at": raw.get("ingested_at") or "2026-10-14T11:00:00Z",
        "source": {
            "channel": raw.get("channel") or "x",
            "handle": raw.get("handle"),
            "role_guess": raw.get("role_guess"),
        },
        "tier_prior": raw.get("tier_prior"),
        "participation": raw.get("participation"),
        "lane_hint": raw.get("lane_hint"),
        "prefilter": raw.get("prefilter"),
        "cluster_id": raw.get("cluster_id"),
        "status_in_pool": raw.get("status_in_pool") or "pending",
        "drop_reason": raw.get("drop_reason"),
        "archive_id": raw.get("archive_id"),
        "promotion_path": raw.get("promotion_path"),
        "notes": raw.get("notes") or "",
    }


def _expect_row(row: dict, spec: dict, name: str) -> None:
    for key in ("status_in_pool", "drop_reason", "prefilter", "tier_prior"):
        if key in spec and row.get(key) != spec[key]:
            raise SystemExit(f"FAIL {name} {row.get('id')} {key}: {row.get(key)!r} != {spec[key]!r}")
    if "role_guess" in spec and (row.get("source") or {}).get("role_guess") != spec["role_guess"]:
        raise SystemExit(
            f"FAIL {name} {row.get('id')} role_guess: {(row.get('source') or {}).get('role_guess')!r}"
        )
    notes = row.get("notes") or ""
    if spec.get("notes_contains") and spec["notes_contains"] not in notes:
        raise SystemExit(f"FAIL {name} {row.get('id')} notes missing {spec['notes_contains']!r}: {notes!r}")
    if spec.get("notes_absent") and spec["notes_absent"] in notes:
        raise SystemExit(f"FAIL {name} {row.get('id')} notes unexpectedly has {spec['notes_absent']!r}: {notes!r}")
    if "archive_id" in spec and row.get("archive_id") != spec["archive_id"]:
        raise SystemExit(f"FAIL {name} archive_id {row.get('archive_id')!r}")
    if spec.get("notes_equals") is not None and notes != spec["notes_equals"]:
        raise SystemExit(f"FAIL {name} notes {notes!r} != {spec['notes_equals']!r}")


def self_check() -> None:
    """Fixture checks. Synthetic text only. Does not fetch RSS."""
    cases_path = ROOT / "testdata" / "gates" / "cases.json"
    if not cases_path.is_file():
        raise SystemExit(f"FAIL: missing {cases_path}")
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    as_of = parse_utc(payload["as_of"])
    options = options_from_repo(as_of)
    rule_ids = {rule["id"] for rule in options.entity_rules}
    for required in ("cve", "examplemodel-9", "fixtureloose-name"):
        if required not in rule_ids:
            raise SystemExit(f"FAIL: entity rule {required} missing")
    if _expected_gate(options.handles["techcrunch-ai"]) != "high":
        raise SystemExit("FAIL: TechCrunch must stay a high-gate report source")
    if _expected_gate(options.handles["openai-blog"]) != "low":
        raise SystemExit("FAIL: OpenAI blog must stay a low-gate primary source")
    if not options.a_tier or not options.practice_handles:
        raise SystemExit("FAIL: config handle lists were not loaded")
    if options.a_tier & options.practice_handles:
        raise SystemExit("FAIL: practice_handles overlap a_tier")
    gh = lookup_domain("https://github.com/openai/openai-python/releases/tag/v9", options.domains)
    if not gh or gh.get("role_guess") != "primary":
        raise SystemExit(f"FAIL: GitHub OpenAI releases should be primary, got {gh}")
    if lookup_domain("https://github.com/someone/repo", options.domains) is not None:
        raise SystemExit("FAIL: bare GitHub repo must not inherit the lab path rule")
    tc = lookup_domain("https://techcrunch.com/2026/10/14/fixture", options.domains)
    hn = lookup_domain("https://news.ycombinator.com/item?id=1", options.domains)
    rd = lookup_domain("https://www.reddit.com/r/LocalLLaMA/comments/fixture", options.domains)
    if not tc or tc.get("role_guess") != "report" or not hn or hn.get("role_guess") != "report":
        raise SystemExit("FAIL: TechCrunch and HN must stay report")
    if not rd or rd.get("role_guess") != "report":
        raise SystemExit("FAIL: Reddit must stay report")

    schema = json.loads((ROOT / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise SystemExit("FAIL: jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    validator = Draft202012Validator(schema)
    allowed_reasons = set(schema["properties"]["drop_reason"]["anyOf"][1]["enum"])
    forbidden = {"pending", "wrong_lane", "quota", "quota_defer"}
    if forbidden & allowed_reasons:
        raise SystemExit(f"FAIL: schema drop_reason contains a non-reason: {forbidden & allowed_reasons}")

    for case in payload["cases"]:
        name = case["name"]
        records = [_expand_fixture_row(raw) for raw in case["rows"]]
        first = annotate_records(records, options)
        second = annotate_records(records, options)
        if [dumps_record(row) for row in first] != [dumps_record(row) for row in second]:
            raise SystemExit(f"FAIL {name}: annotate is not deterministic")
        by_id = {row["id"]: row for row in first}
        for rid, spec in (case.get("expect") or {}).items():
            if rid not in by_id:
                raise SystemExit(f"FAIL {name}: missing {rid}")
            _expect_row(by_id[rid], spec, name)
        for group in case.get("same_cluster") or []:
            ids = {by_id[rid]["cluster_id"] for rid in group}
            if len(ids) != 1 or None in ids:
                raise SystemExit(f"FAIL {name}: expected one cluster for {group}, got {ids}")
        for group in case.get("different_cluster") or []:
            ids = [by_id[rid]["cluster_id"] for rid in group]
            if len(set(ids)) != len(ids):
                raise SystemExit(f"FAIL {name}: clusters should differ for {group}: {ids}")
        for row in first:
            errors = sorted(validator.iter_errors(row), key=lambda err: list(err.path))
            if errors:
                raise SystemExit(f"FAIL {name} schema {row['id']}: {errors[0].message}")
            reason = row.get("drop_reason")
            if reason in forbidden:
                raise SystemExit(f"FAIL {name}: invented drop_reason {reason}")
            if row["status_in_pool"] == "dropped" and reason not in allowed_reasons:
                raise SystemExit(f"FAIL {name}: bad drop_reason {reason}")
            if row["status_in_pool"] != "dropped" and reason is not None:
                raise SystemExit(f"FAIL {name}: {row['status_in_pool']} must not carry {reason}")
            if row.get("title") is None and not isinstance(row.get("cluster_id"), str):
                raise SystemExit(f"FAIL {name}: missing title crashed clustering for {row['id']}")

    # Policy switches are explicit. The fixture default stays defer / pending.
    stale_src = _expand_fixture_row(
        {
            "id": "cand-20261010-aaaaaaaaaaaa",
            "url": "https://openai.com/blog/fixture-stale-policy",
            "snippet": "FIXTURE agents model note",
            "published_at": "2026-10-10T00:00:00Z",
            "handle": "openai-blog",
            "channel": "rss",
        }
    )
    dropped = annotate_records([stale_src], options_from_repo(as_of, stale_policy="drop"))[0]
    if dropped["status_in_pool"] != "dropped" or dropped["drop_reason"] != "stale_old":
        raise SystemExit(f"FAIL stale-policy drop: {dropped['status_in_pool']} {dropped['drop_reason']}")
    timed = annotate_records(
        [
            _expand_fixture_row(
                {
                    "id": "cand-20261014-bbbbbbbbbbbb",
                    "url": "https://openai.com/blog/fixture-no-time",
                    "snippet": "FIXTURE agents model note",
                    "published_at": None,
                    "handle": "openai-blog",
                    "channel": "rss",
                }
            )
        ],
        options_from_repo(as_of, no_time_policy="drop"),
    )[0]
    if timed["drop_reason"] != "no_reliable_time" or timed["status_in_pool"] != "dropped":
        raise SystemExit(f"FAIL no-time-policy drop: {timed['status_in_pool']} {timed['drop_reason']}")

    public_out = ROOT / "public" / "_gates_should_not_write.jsonl"
    try:
        write_batch(public_out, [])
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: annotate wrote under public/")
    if public_out.exists():
        public_out.unlink()
        raise SystemExit("FAIL: public jsonl was created")

    seen_a = _expand_fixture_row(
        {
            "id": "cand-20261014-0000000000aa",
            "url": "https://openai.com/blog/fixture-seen-a",
            "snippet": "FIXTURE agents first copy",
            "published_at": "2026-10-14T08:00:00Z",
            "handle": "openai-blog",
            "channel": "rss",
        }
    )
    seen_b = _expand_fixture_row(
        {
            "id": "cand-20261014-0000000000aa",
            "url": "https://openai.com/index/fixture-seen-b",
            "snippet": "FIXTURE agents second copy with extra pricing context",
            "published_at": "2026-10-14T09:00:00Z",
            "handle": "openai-blog",
            "channel": "rss",
        }
    )
    seen_rows = annotate_records([seen_a, seen_b], options)
    if seen_rows[0]["status_in_pool"] != "active" or seen_rows[1]["drop_reason"] != "duplicate_url":
        raise SystemExit(
            f"FAIL seen id: {seen_rows[0]['status_in_pool']} {seen_rows[1]['status_in_pool']} {seen_rows[1]['drop_reason']}"
        )

    hand = _expand_fixture_row(
        {
            "id": "cand-20261010-0000000000ab",
            "url": "https://x.com/karpathy/status/42",
            "snippet": "FIXTURE agents already judged",
            "published_at": "2026-10-10T00:00:00Z",
            "handle": "karpathy",
            "status_in_pool": "active",
            "prefilter": "PASS",
            "tier_prior": "a_tier",
            "notes": "editor hand",
        }
    )
    held = annotate_records([hand], options_from_repo(as_of, only_pending=True))[0]
    if held["status_in_pool"] != "active" or held["notes"] != "editor hand":
        raise SystemExit(f"FAIL only-pending clobbered a judged row: {held['status_in_pool']} {held['notes']!r}")
    skipped = _expand_fixture_row(
        {
            "id": "cand-20261014-0000000000ac",
            "url": "https://x.com/karpathy/status/43",
            "snippet": "FIXTURE agents",
            "published_at": "2026-10-14T10:00:00Z",
            "handle": "karpathy",
            "status_in_pool": "dropped",
            "drop_reason": "editor_skip",
            "prefilter": "PASS",
            "notes": "editor said skip",
        }
    )
    kept_skip = annotate_records([skipped], options)[0]
    if kept_skip["drop_reason"] != "editor_skip" or kept_skip["notes"] != "editor said skip":
        raise SystemExit("FAIL editor_skip must stay a true drop and keep its note")
    low_scored = _expand_fixture_row(
        {
            "id": "cand-20261014-0000000000ae",
            "url": "https://x.com/karpathy/status/45",
            "snippet": "FIXTURE agents",
            "published_at": "2026-10-14T10:00:00Z",
            "handle": "karpathy",
            "status_in_pool": "dropped",
            "drop_reason": "low_score",
            "prefilter": "PASS",
            "notes": "score:low_score value=0.1000",
        }
    )
    kept_low = annotate_records([low_scored], options)[0]
    if kept_low["drop_reason"] != "low_score" or kept_low["notes"] != "score:low_score value=0.1000":
        raise SystemExit("FAIL low_score must stay a true drop and keep its trace")
    rerouted = _expand_fixture_row(
        {
            "id": "cand-20261014-0000000000ad",
            "url": "https://x.com/op7418/status/44",
            "snippet": "FIXTURE agents steps",
            "published_at": "2026-10-10T00:00:00Z",
            "handle": "op7418",
            "status_in_pool": "rerouted",
            "lane_hint": "practice",
            "prefilter": "PASS",
            "notes": "moved lane",
        }
    )
    kept_route = annotate_records([rerouted], options)[0]
    if kept_route["status_in_pool"] != "rerouted" or kept_route["drop_reason"] is not None:
        raise SystemExit("FAIL rerouted is not a drop and must not be rewritten")

    import tempfile

    sample = _expand_fixture_row(
        {
            "id": "cand-20261014-000000000001",
            "url": "https://openai.com/blog/fixture-pass",
            "channel": "rss",
            "handle": "openai-blog",
            "published_at": "2026-10-14T01:00:00Z",
            "snippet": "FIXTURE agents model release for the same Shanghai day",
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        pool = Path(tmp) / "pool"
        merge_pool(pool, [sample], "2026-10-14T11:00:00Z")
        pairs = read_pool(pool)
        written = annotate_records([row for _path, row in pairs], options)
        write_pool(pool, pairs, written)
        day = pool / "candidates" / "2026-10-14.jsonl"
        if json.loads(day.read_text(encoding="utf-8"))["status_in_pool"] != "active":
            raise SystemExit("FAIL: pool rewrite did not keep the PASS row active")
        before = day.read_bytes()
        pairs = read_pool(pool)
        again = annotate_records([row for _path, row in pairs], options_from_repo(as_of, only_pending=True))
        write_pool(pool, pairs, again)
        if day.read_bytes() != before:
            raise SystemExit("FAIL: --only-pending rewrote a row that was already annotated")
    print("OK annotate_gates self-check")


def _utc_now() -> str:
    if __package__ in {None, ""}:
        from card_times import utc_now_iso
    else:
        from .card_times import utc_now_iso
    return utc_now_iso()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Annotate candidate rows with L0 gates and L2 cluster ids.")
    parser.add_argument("--input", "-i", help="JSONL or JSON records. Default: stdin when --out is set without --pool-dir.")
    parser.add_argument("--out", help="Overwrite this JSONL. Local fixtures and CI. Refuses public/.")
    parser.add_argument("--pool-dir", help="Pool repo root. Rewrites candidates/*.jsonl in place. Not combined with --input.")
    parser.add_argument("--as-of", help="ISO-8601 UTC clock for stale / backfill. Default: now.")
    parser.add_argument("--stale-hours", type=float, default=48)
    parser.add_argument("--stale-policy", choices=("defer", "drop"), default="defer")
    parser.add_argument("--no-time-policy", choices=("pending", "drop"), default="pending")
    parser.add_argument("--same-source-window-minutes", type=int, default=30)
    parser.add_argument("--no-new-info-days", type=int, default=7)
    parser.add_argument(
        "--only-pending",
        action="store_true",
        help="Skip rows that already have a prefilter or a non-pending status.",
    )
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if args.input and args.pool_dir:
        parser.error("pass --pool-dir to rewrite the pool, or --input with --out. Not both.")
    if not args.out and not args.pool_dir:
        parser.error("pass --out and/or --pool-dir")
    try:
        as_of = parse_utc(args.as_of) if args.as_of else parse_utc(_utc_now())
        options = options_from_repo(
            as_of,
            stale_hours=args.stale_hours,
            stale_policy=args.stale_policy,
            no_time_policy=args.no_time_policy,
            same_source_window_minutes=args.same_source_window_minutes,
            no_new_info_days=args.no_new_info_days,
            only_pending=args.only_pending,
        )
        pool_dir = Path(args.pool_dir) if args.pool_dir else None
        pool_pairs = None
        if pool_dir is not None:
            pool_pairs = read_pool(pool_dir)
            records = [row for _path, row in pool_pairs]
        elif args.input:
            records = load_records(Path(args.input).read_text(encoding="utf-8"))
        else:
            records = load_records(sys.stdin.read())
        if not records:
            print("无更新")
            return 0
        return run_paths(records, options, Path(args.out) if args.out else None, pool_pairs, pool_dir)
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
