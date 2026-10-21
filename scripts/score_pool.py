#!/usr/bin/env python3
"""Score candidate rows after annotate gates and before promotion.

score ≈ prior(tier, smoothed hit rate)
      × exp(-age_hours / τ)
      × corroboration(independent sources, primary link)
      × velocity(bookmark/like vs author baseline)
      + actionability (capped rule heuristic)

Bands written onto the row:
  auto_brief  high score, the row itself comes from an official source on an
              AUTO_CHANNELS feed (not X, not a cluster neighbour), and not practice
  review      mid/high, practice, deferred, cluster-only primary, or no primary
  drop        low score → status dropped, drop_reason low_score, notes keep the trace

Hit rate counts promoted rows and published briefs as hits. Only editorial or
quality drops (QUALITY_DROPS) are misses; decay, duplicates, and timing are not
a verdict on the source. Rows that already carry brief_id are a decision and
are not rescored. editor_skip, promoted, and rerouted rows are left untouched.
Only rows ingested within score_window_days are rescored, so older pool files
are not rewritten on every run.

Rules scoring does not call a network. AI_RADAR_SCORE_LLM_URL only fills
score.llm.skipped_reason; there is no hosted adapter in this repo.

  python3 scripts/score_pool.py --self-check
  python3 scripts/score_pool.py --pool-dir ../ai-radar-pool --write-review
  python3 scripts/score_pool.py --input rows.jsonl --out /tmp/scored.jsonl \\
      --as-of 2026-10-14T12:00:00Z

Refuses to write under public/. Practice rows are never auto_brief.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import (
        evidence_links,
        has_primary_ref,
        options_from_repo,
        read_pool,
        write_pool,
    )
    from card_times import utc_now_iso
    from ingest_x import (
        IngestError,
        assert_not_public,
        dumps_record,
        parse_utc,
        shanghai_file_day,
        write_batch,
    )
    from shift_ingest_x_to_pool import assert_shift_pool_dir
else:
    from .annotate_gates import (
        evidence_links,
        has_primary_ref,
        options_from_repo,
        read_pool,
        write_pool,
    )
    from .card_times import utc_now_iso
    from .ingest_x import (
        IngestError,
        assert_not_public,
        dumps_record,
        parse_utc,
        shanghai_file_day,
        write_batch,
    )
    from .shift_ingest_x_to_pool import assert_shift_pool_dir

ROOT = Path(__file__).resolve().parents[1]

STEP_RE = re.compile(
    r"步骤|首先|然后|接着|安装|运行|"
    r"\b(?:step\s*[0-9]|install|how to|docker compose|pip install|npm install)\b",
    re.I,
)
CMD_RE = re.compile(
    r"(?:^|\n)\s*(?:\$ |```)|(?:^|\n)\s*(?:pip3?|npm|pnpm|docker|git|curl|uv)\s+\S",
    re.I,
)
REPO_RE = re.compile(
    r"https?://(?:github\.com|gitlab\.com)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.I,
)
LOW_SCORE_NOTE_RE = re.compile(r"\s*score:low_score\b.*$")

TIER_WEIGHT = {
    "T1": 0.95,
    "a_tier": 0.92,
    "T2": 0.78,
    "practice": 0.70,
    "T3": 0.45,
}
ROLE_WEIGHT = {"primary": 0.95, "analysis": 0.72, "report": 0.42}
UNKNOWN_TIER = 0.48
AUTO_CHANNELS = frozenset({"rss"})
QUALITY_DROPS = frozenset({
    "editor_skip",
    "prefilter_block",
    "not_opc_action",
    "rumor_no_upgrade",
    "media_alone",
    "practice_not_steps",
    "hot_signal_only",
})


@dataclass
class ScoreConfig:
    tau_hours: float = 36.0
    auto_min: float = 0.52
    review_min: float = 0.34
    hit_alpha: float = 2.0
    hit_beta: float = 2.0
    tier_mix: float = 0.7
    bookmark_prior: float = 3.0
    like_prior: float = 5.0
    author_prior_n: float = 3.0
    actionability_cap: float = 0.12
    score_window_days: float = 3.0

    def validate(self) -> None:
        if self.tau_hours <= 0:
            raise IngestError("score.tau_hours must be > 0")
        if not 0 <= self.review_min <= self.auto_min <= 1:
            raise IngestError("score thresholds must satisfy 0 ≤ review_min ≤ auto_min ≤ 1")
        if self.hit_alpha < 0 or self.hit_beta < 0:
            raise IngestError("score hit prior must be ≥ 0")
        if not 0 < self.tier_mix < 1:
            raise IngestError("score.tier_mix must be between 0 and 1")
        if self.bookmark_prior <= 0 or self.like_prior <= 0 or self.author_prior_n <= 0:
            raise IngestError("score bookmark/like prior is invalid")
        if self.actionability_cap < 0 or self.actionability_cap > 0.5:
            raise IngestError("score.actionability_cap must be in [0, 0.5]")
        if self.score_window_days <= 0:
            raise IngestError("score.score_window_days must be > 0")


def load_score_config(root: Path | None = None) -> ScoreConfig:
    root = root or ROOT
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    raw = cfg.get("score") or {}
    if not isinstance(raw, dict):
        raise IngestError("config.json score must be an object")
    fields = {name: raw[name] for name in ScoreConfig.__dataclass_fields__ if name in raw}
    loaded = ScoreConfig(**fields)
    loaded.validate()
    return loaded


def smoothed_bookmark_like(
    bookmarks: float,
    likes: float,
    bookmark_prior: float = 3.0,
    like_prior: float = 5.0,
) -> float:
    """Bayesian bookmark÷like. Small samples stay near the prior, not the raw ratio."""
    return (float(bookmarks) + bookmark_prior) / (float(likes) + like_prior)


def smoothed_hit_rate(hits: float, drops: float, alpha: float = 2.0, beta: float = 2.0) -> float:
    """Hit rate with discarded rows in the denominator. Alpha/beta keep an empty history at 0.5."""
    return (float(hits) + alpha) / (float(hits) + float(drops) + alpha + beta)


def llm_slot() -> dict | None:
    """Reserved structured judge. Does not open a socket."""
    url = (os.environ.get("AI_RADAR_SCORE_LLM_URL") or "").strip()
    if not url:
        return None
    return {"skipped_reason": "adapter_not_configured"}


def _r4(value: float) -> float:
    return round(float(value), 4)


def handle_of(row: dict) -> str | None:
    handle = (row.get("source") or {}).get("handle")
    if isinstance(handle, str) and handle.strip():
        return handle.strip().lower()
    return None


def is_practice_row(row: dict, practice_handles: set[str]) -> bool:
    handle = handle_of(row) or ""
    if handle in practice_handles:
        return True
    if row.get("tier_prior") == "practice":
        return True
    if row.get("lane_hint") == "practice" or row.get("participation") == "practice":
        return True
    return False


def row_is_primary(row: dict, options) -> bool:
    if (row.get("source") or {}).get("role_guess") == "primary":
        return True
    return has_primary_ref(row, options)


def is_official_row(row: dict) -> bool:
    """The row itself is an official feed. Cluster neighbours and X posts do not qualify."""
    source = row.get("source") or {}
    return source.get("role_guess") == "primary" and source.get("channel") in AUTO_CHANNELS


def _pass_row(row: dict) -> bool:
    return row.get("prefilter") == "PASS"


def decision_counts(rows: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Promoted rows and published briefs are hits. Editorial or quality drops are misses.

    low_score (decay), duplicate_*, no_new_info, stale_old, and missing clocks say
    nothing about the source, so they stay out of the denominator. The same id counts once.
    """
    hits: dict[str, set[str]] = defaultdict(set)
    drops: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        handle = handle_of(row)
        if not handle:
            continue
        rid = str(row.get("id") or "")
        status = row.get("status_in_pool")
        if status == "promoted" or row.get("brief_id"):
            hits[handle].add(rid)
            drops[handle].discard(rid)
        elif status == "dropped" and row.get("drop_reason") in QUALITY_DROPS and rid not in hits[handle]:
            drops[handle].add(rid)
    return (
        {handle: len(ids) for handle, ids in hits.items()},
        {handle: len(ids) for handle, ids in drops.items()},
    )


def _count(value) -> float:
    """Engagement counts from a fetch. Negative, non-numeric, or missing values read as 0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or number < 0:
        return 0.0
    return number


def engagement_ratio(row: dict, cfg: ScoreConfig) -> float | None:
    engagement = row.get("engagement")
    if not isinstance(engagement, dict):
        return None
    if "likes" not in engagement and "bookmarks" not in engagement:
        return None
    return smoothed_bookmark_like(
        _count(engagement.get("bookmarks")),
        _count(engagement.get("likes")),
        cfg.bookmark_prior,
        cfg.like_prior,
    )


def engagement_rate(row: dict, age_hours: float, cfg: ScoreConfig) -> float | None:
    engagement = row.get("engagement")
    if not isinstance(engagement, dict):
        return None
    if "likes" not in engagement and "bookmarks" not in engagement:
        return None
    bookmarks = _count(engagement.get("bookmarks"))
    return (bookmarks + cfg.bookmark_prior) / (max(age_hours, 0.0) + 1.0)


def age_hours(row: dict, as_of: datetime) -> float | None:
    """Hours since publish. A clock more than an hour in the future is unreliable, not fresh."""
    raw = row.get("published_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        published = parse_utc(raw)
    except IngestError:
        return None
    hours = (as_of - published).total_seconds() / 3600.0
    if hours < -1.0:
        return None
    return max(0.0, hours)


def tier_base(row: dict) -> float:
    tier = row.get("tier_prior")
    role = (row.get("source") or {}).get("role_guess")
    base = TIER_WEIGHT.get(tier) if isinstance(tier, str) else None
    role_weight = ROLE_WEIGHT.get(role) if isinstance(role, str) else None
    if base is None and role_weight is None:
        return UNKNOWN_TIER
    if base is None:
        return role_weight or UNKNOWN_TIER
    if role_weight is None:
        return base
    return max(base, role_weight)


def source_identity(row: dict) -> str:
    handle = handle_of(row)
    if handle:
        return "h:" + handle
    return "d:" + str(row.get("url_norm") or row.get("id") or "")


def cluster_key(row: dict) -> str:
    cid = row.get("cluster_id")
    if isinstance(cid, str) and cid:
        return cid
    return "id:" + str(row.get("id") or "")


def actionability(row: dict, cap: float) -> float:
    parts = [row.get("title"), row.get("snippet"), row.get("url"), row.get("url_norm")]
    text = "\n".join(part for part in parts if isinstance(part, str))
    score = 0.0
    if STEP_RE.search(text):
        score += 0.05
    if CMD_RE.search(text):
        score += 0.04
    if REPO_RE.search(text):
        score += 0.04
    return _r4(min(cap, score))


def decay_of(row: dict, as_of: datetime, tau_hours: float) -> float:
    age = age_hours(row, as_of)
    if age is None:
        return 0.55
    return math.exp(-age / tau_hours)


def _low_score_notes(notes: str, trace: str) -> str:
    kept = LOW_SCORE_NOTE_RE.sub("", notes or "").strip()
    if kept:
        return f"{kept} {trace}"
    return trace


def band_of(
    value: float,
    primary: bool,
    practice: bool,
    status: str,
    cfg: ScoreConfig,
    official: bool = False,
) -> tuple[str, str]:
    if value < cfg.review_min:
        return "drop", "drop_low_score"
    if practice:
        return "review", "review_practice"
    if status == "deferred":
        return "review", "review_deferred"
    if not primary:
        return "review", "review_no_primary"
    if not official:
        return "review", "review_not_official"
    if value >= cfg.auto_min and status == "active":
        return "auto_brief", "auto_primary"
    if value >= cfg.review_min:
        return "review", "review_score"
    return "drop", "drop_low_score"


def scorable(row: dict) -> bool:
    if row.get("status_in_pool") in {"promoted", "rerouted", "dropped", "pending"}:
        return False
    if row.get("brief_id"):
        return False
    if row.get("drop_reason") in {"editor_skip", "low_score"}:
        return False
    if row.get("prefilter") != "PASS":
        return False
    return row.get("status_in_pool") in {"active", "deferred"}


def in_score_window(row: dict, as_of: datetime, days: float) -> bool:
    """Rows ingested long ago keep their last score instead of being rewritten every run."""
    raw = row.get("ingested_at")
    if not isinstance(raw, str) or not raw:
        return True
    try:
        ingested = parse_utc(raw)
    except IngestError:
        return True
    return (as_of - ingested).total_seconds() <= days * 86400.0


def score_records(rows: list[dict], options, cfg: ScoreConfig, as_of: datetime) -> list[dict]:
    """Return new row dicts. Input dicts are not mutated."""
    cfg.validate()
    copied = [json.loads(dumps_record(row)) for row in rows]
    hits, drops = decision_counts(copied)
    identities: dict[str, set[str]] = defaultdict(set)
    primary_cluster: set[str] = set()
    ratios: dict[str, list[float]] = defaultdict(list)
    rates: dict[str, list[float]] = defaultdict(list)
    ages = [age_hours(row, as_of) for row in copied]
    for row, age in zip(copied, ages):
        if not _pass_row(row):
            continue
        identities[cluster_key(row)].add(source_identity(row))
        if row_is_primary(row, options):
            primary_cluster.add(cluster_key(row))
        handle = handle_of(row)
        ratio = engagement_ratio(row, cfg)
        if handle and ratio is not None:
            ratios[handle].append(ratio)
        rate = engagement_rate(row, age if age is not None else 6.0, cfg)
        if handle and rate is not None:
            rates[handle].append(rate)

    global_ratio = cfg.bookmark_prior / cfg.like_prior
    prior_rate = cfg.bookmark_prior / 7.0
    llm = llm_slot()
    for row, age in zip(copied, ages):
        if not scorable(row) or not in_score_window(row, as_of, cfg.score_window_days):
            continue
        handle = handle_of(row)
        hit = smoothed_hit_rate(
            hits.get(handle or "", 0),
            drops.get(handle or "", 0),
            cfg.hit_alpha,
            cfg.hit_beta,
        )
        base = tier_base(row)
        prior = _r4(cfg.tier_mix * base + (1.0 - cfg.tier_mix) * hit)
        decay = _r4(decay_of(row, as_of, cfg.tau_hours))
        members = identities.get(cluster_key(row), {source_identity(row)})
        extras = min(3, max(0, len(members) - 1))
        primary = cluster_key(row) in primary_cluster or row_is_primary(row, options)
        corroboration = _r4(min(1.0, 0.72 + extras * 0.08 + (0.16 if primary else 0.0)))
        velocity = 1.0
        if handle and handle in ratios and engagement_ratio(row, cfg) is not None:
            baseline_ratio = (sum(ratios[handle]) + global_ratio * cfg.author_prior_n) / (
                len(ratios[handle]) + cfg.author_prior_n
            )
            baseline_rate = (sum(rates[handle]) + prior_rate * cfg.author_prior_n) / (
                len(rates[handle]) + cfg.author_prior_n
            )
            quality = engagement_ratio(row, cfg) / baseline_ratio
            speed = engagement_rate(row, age if age is not None else 6.0, cfg) / baseline_rate
            relative = 0.5 * quality + 0.5 * speed
            lifted = 1.0 + 0.45 * math.tanh(math.log(max(relative, 1e-6)))
            velocity = _r4(min(1.35, max(0.55, lifted)))
        act = actionability(row, cfg.actionability_cap)
        value = _r4(min(1.0, max(0.0, prior * decay * corroboration * velocity + act)))
        practice = is_practice_row(row, options.practice_handles)
        status = str(row.get("status_in_pool") or "")
        official = is_official_row(row)
        band, reason = band_of(value, primary, practice, status, cfg, official)
        row["score"] = {
            "value": value,
            "band": band,
            "band_reason": reason,
            "primary_source": bool(primary),
            "official_source": bool(official),
            "method": "rules",
            "components": {
                "prior": prior,
                "decay": decay,
                "corroboration": corroboration,
                "velocity": velocity,
                "actionability": act,
            },
            "llm": llm,
        }
        if band == "drop":
            trace = (
                f"score:low_score value={value:.4f} prior={prior:.4f} decay={decay:.4f} "
                f"corroboration={corroboration:.4f} velocity={velocity:.4f} actionability={act:.4f}"
            )
            row["status_in_pool"] = "dropped"
            row["drop_reason"] = "low_score"
            row["notes"] = _low_score_notes(str(row.get("notes") or ""), trace)
            row["archive_id"] = None
            row["promotion_path"] = None
    return copied


def review_markdown(rows: list[dict], as_of: datetime) -> str:
    """Human queue. No raw post body. Practice stays on this list, not on the practice page."""
    day = shanghai_file_day(as_of.strftime("%Y-%m-%dT%H:%M:%SZ"))
    queued = []
    for row in rows:
        score = row.get("score") or {}
        if score.get("band") != "review":
            continue
        if row.get("status_in_pool") == "dropped":
            continue
        queued.append(row)
    queued.sort(key=lambda row: (-(row.get("score") or {}).get("value", 0), str(row.get("id"))))
    lines = [
        f"# 审核清单 {day}",
        "",
        "机器低分已是 `dropped` + `low_score`，不在本清单。实操只出现在这里，不写入 practice inbox。",
        "通过并上 L1：池行改为 `promoted`，`archive_id` 指向公开卡，公开卡写同一个 `candidate_id`。",
        "否决：`drop_reason=editor_skip`，并且 `notes` 不能空。`annotate_gates` 和 `score_pool` 都不再改这一行。",
        "私人 action（tried / ignored）写未跟踪的 `owner-actions.local.json`，或飞书。不要写入公开 `public/owner-actions.json`。",
        "",
        "| cid | band | value | handle | lane | primary | url |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in queued:
        score = row["score"]
        handle = handle_of(row) or ""
        if row.get("lane_hint") == "practice" or row.get("tier_prior") == "practice" or score.get("band_reason") == "review_practice":
            lane = "practice"
        else:
            lane = row.get("lane_hint") or "digest"
        lines.append(
            "| {cid} | {band} | {value:.4f} | {handle} | {lane} | {primary} | {url} |".format(
                cid=row.get("id"),
                band=score.get("band_reason"),
                value=float(score.get("value") or 0),
                handle=handle,
                lane=lane,
                primary="yes" if score.get("primary_source") else "no",
                url=row.get("url_norm") or row.get("url") or "",
            )
        )
    if not queued:
        lines.append("|  |  |  |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def write_review(pool_dir: Path, rows: list[dict], as_of: datetime) -> Path:
    assert_shift_pool_dir(pool_dir)
    day = shanghai_file_day(as_of.strftime("%Y-%m-%dT%H:%M:%SZ"))
    path = pool_dir / "review" / f"{day}.md"
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(review_markdown(rows, as_of), encoding="utf-8")
    return path


def run_score(
    rows: list[dict],
    as_of: datetime,
    cfg: ScoreConfig,
    options,
    out: Path | None,
    pool_pairs,
    pool_dir: Path | None,
    review: bool,
) -> tuple[list[dict], int]:
    scored = score_records(rows, options, cfg, as_of)
    if out is not None:
        write_batch(out, scored)
        print(f"OK score_pool: wrote {out}")
    if pool_dir is not None and pool_pairs is not None:
        write_pool(pool_dir, pool_pairs, scored)
        print(f"OK score_pool: pool {pool_dir}")
    if review:
        if pool_dir is None:
            raise IngestError("--write-review needs --pool-dir")
        path = write_review(pool_dir, scored, as_of)
        print(f"OK score_pool: review {path}")
    bands: dict[str, int] = defaultdict(int)
    for row in scored:
        band = (row.get("score") or {}).get("band")
        if band:
            bands[band] += 1
    print(
        "OK score_pool: "
        f"auto_brief={bands['auto_brief']} review={bands['review']} drop={bands['drop']} "
        f"as_of={as_of.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    return scored, 0


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _fixture(**kwargs) -> dict:
    row = {
        "schema_version": 1,
        "id": kwargs["id"],
        "url": kwargs["url"],
        "url_norm": kwargs["url"],
        "title": kwargs.get("title"),
        "snippet": kwargs.get("snippet"),
        "published_at": kwargs.get("published_at", "2026-10-14T10:00:00Z"),
        "ingested_at": "2026-10-14T11:00:00Z",
        "source": {
            "channel": kwargs.get("channel", "rss"),
            "handle": kwargs.get("handle"),
            "role_guess": kwargs.get("role_guess"),
        },
        "tier_prior": kwargs.get("tier_prior"),
        "participation": kwargs.get("participation"),
        "lane_hint": kwargs.get("lane_hint"),
        "prefilter": kwargs.get("prefilter", "PASS"),
        "cluster_id": kwargs.get("cluster_id", "clu-scorefixture1"),
        "status_in_pool": kwargs.get("status", "active"),
        "drop_reason": kwargs.get("drop_reason"),
        "archive_id": kwargs.get("archive_id"),
        "promotion_path": kwargs.get("promotion_path"),
        "notes": kwargs.get("notes", ""),
    }
    if "engagement" in kwargs:
        row["engagement"] = kwargs["engagement"]
    return row


def self_check() -> None:
    """Synthetic rows only. Does not read a private pool or call a model."""
    os.environ.pop("AI_RADAR_SCORE_LLM_URL", None)
    if llm_slot() is not None:
        raise SystemExit("FAIL: rules path must leave llm null when the endpoint is unset")
    os.environ["AI_RADAR_SCORE_LLM_URL"] = "https://example.invalid/score"
    try:
        marked = llm_slot()
        if not marked or marked.get("skipped_reason") != "adapter_not_configured":
            raise SystemExit(f"FAIL: llm slot {marked}")
    finally:
        os.environ.pop("AI_RADAR_SCORE_LLM_URL", None)

    raw_ratio = 200 / 10
    smooth = smoothed_bookmark_like(200, 10)
    if not smooth < raw_ratio:
        raise SystemExit(f"FAIL: smoothed bookmark/like {smooth} should sit below raw {raw_ratio}")
    if not smoothed_bookmark_like(0, 1) > 0:
        raise SystemExit("FAIL: empty bookmarks must stay above zero after the prior")
    quiet_history = smoothed_hit_rate(1, 0)
    dropped_history = smoothed_hit_rate(1, 6)
    if not dropped_history < quiet_history:
        raise SystemExit("FAIL: discarded rows must lower hit rate")

    cfg = load_score_config(ROOT)
    as_of = parse_utc("2026-10-14T12:00:00Z")
    options = options_from_repo(as_of)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise SystemExit("FAIL: jsonschema is not installed. Run: pip install -r requirements-ci.txt")
    schema = json.loads((ROOT / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    fresh = _fixture(
        id="cand-20261014-aaaaaaaaaaa1",
        url="https://openai.com/blog/fixture-score-primary",
        handle="openai-blog",
        role_guess="primary",
        tier_prior="T1",
        title="FIXTURE model weights are up",
        snippet="FIXTURE a model release note.",
        cluster_id="clu-scoreprimary1",
    )
    practice = _fixture(
        id="cand-20261014-aaaaaaaaaaa2",
        url="https://x.com/op7418/status/501",
        channel="x",
        handle="op7418",
        tier_prior="practice",
        snippet="FIXTURE model 步骤：pip install fixture-tool https://github.com/example/fixture-tool",
        cluster_id="clu-scorepractice",
    )
    stale = _fixture(
        id="cand-20261001-aaaaaaaaaaa3",
        url="https://x.com/randomperson/status/9",
        channel="x",
        handle="randomperson",
        published_at="2026-10-01T00:00:00Z",
        snippet="FIXTURE model mention that is old.",
        cluster_id="clu-scorestale001",
    )
    skipped = _fixture(
        id="cand-20261014-aaaaaaaaaaa4",
        url="https://x.com/karpathy/status/70",
        channel="x",
        handle="karpathy",
        tier_prior="a_tier",
        status="dropped",
        drop_reason="editor_skip",
        notes="editor said skip",
        cluster_id="clu-scoreskip0001",
    )
    promoted = _fixture(
        id="cand-20261014-aaaaaaaaaaa5",
        url="https://openai.com/blog/fixture-score-promoted",
        handle="openai-blog",
        role_guess="primary",
        tier_prior="T1",
        status="promoted",
        archive_id="evt-20261014-fixture-score",
        promotion_path="normal",
        notes="already public",
        cluster_id="clu-scorepromo001",
    )
    deferred = _fixture(
        id="cand-20261014-aaaaaaaaaaa6",
        url="https://openai.com/blog/fixture-score-deferred",
        handle="openai-blog",
        role_guess="primary",
        tier_prior="T1",
        status="deferred",
        title="FIXTURE model held for the next shift",
        snippet="FIXTURE model release, not this slot.",
        cluster_id="clu-scoredefer001",
    )
    no_primary = _fixture(
        id="cand-20261014-aaaaaaaaaaa7",
        url="https://x.com/karpathy/status/77",
        channel="x",
        handle="karpathy",
        tier_prior="a_tier",
        snippet="FIXTURE model note without an official link.",
        cluster_id="clu-scorenoprim01",
    )
    blocked = _fixture(
        id="cand-20261014-aaaaaaaaaaa8",
        url="https://x.com/someone/status/8",
        channel="x",
        handle="someone",
        status="dropped",
        drop_reason="prefilter_block",
        prefilter="BLOCK",
        notes="gate:block",
        cluster_id="clu-scoreblock001",
    )
    solo = _fixture(
        id="cand-20261014-aaaaaaaaaaa9",
        url="https://techcrunch.com/2026/10/14/fixture-score-solo",
        handle="techcrunch-ai",
        role_guess="report",
        tier_prior="T3",
        snippet="FIXTURE model rumor from one desk.",
        cluster_id="clu-scoresolo0001",
    )
    pair_report = _fixture(
        id="cand-20261014-aaaaaaaaaa10",
        url="https://techcrunch.com/2026/10/14/fixture-score-pair",
        handle="techcrunch-ai",
        role_guess="report",
        tier_prior="T3",
        snippet="FIXTURE model note pointing at https://openai.com/blog/fixture-score-pair",
        cluster_id="clu-scorepair0001",
    )
    pair_primary = _fixture(
        id="cand-20261014-aaaaaaaaaa11",
        url="https://openai.com/blog/fixture-score-pair",
        handle="openai-blog",
        role_guess="primary",
        tier_prior="T1",
        title="FIXTURE model pair",
        snippet="FIXTURE model release used as the primary link.",
        cluster_id="clu-scorepair0001",
    )
    viral = _fixture(
        id="cand-20261014-aaaaaaaaaa12",
        url="https://x.com/velocitylab/status/1",
        channel="x",
        handle="velocitylab",
        snippet="FIXTURE model velocity high.",
        cluster_id="clu-scoreviral001",
        engagement={"likes": 10, "bookmarks": 200, "captured_at": "2026-10-14T11:00:00Z"},
    )
    quiet = _fixture(
        id="cand-20261014-aaaaaaaaaa13",
        url="https://x.com/velocitylab/status/2",
        channel="x",
        handle="velocitylab",
        snippet="FIXTURE model velocity low.",
        cluster_id="clu-scorequiet001",
        engagement={"likes": 10, "bookmarks": 0, "captured_at": "2026-10-14T11:00:00Z"},
    )
    plain = _fixture(
        id="cand-20261014-aaaaaaaaaa14",
        url="https://x.com/randomperson/status/14",
        channel="x",
        handle="randomperson",
        snippet="FIXTURE model without steps.",
        cluster_id="clu-scoreplain001",
    )
    steps = _fixture(
        id="cand-20261014-aaaaaaaaaa15",
        url="https://x.com/randomperson/status/15",
        channel="x",
        handle="randomperson",
        snippet="FIXTURE model 步骤：pip install fixture-tool https://github.com/example/fixture-repo",
        cluster_id="clu-scoresteps001",
    )

    batch = [
        fresh, practice, stale, skipped, promoted, deferred, no_primary, blocked,
        solo, pair_report, pair_primary, viral, quiet, plain, steps,
    ]
    first = score_records(batch, options, cfg, as_of)
    second = score_records(batch, options, cfg, as_of)
    if [dumps_record(row) for row in first] != [dumps_record(row) for row in second]:
        raise SystemExit("FAIL: score_pool is not deterministic")
    by_id = {row["id"]: row for row in first}

    def need(rid: str, band: str, reason: str) -> dict:
        row = by_id[rid]
        score = row.get("score") or {}
        if score.get("band") != band or score.get("band_reason") != reason:
            raise SystemExit(
                f"FAIL {rid} band {score.get('band')}/{score.get('band_reason')} "
                f"value={score.get('value')} components={score.get('components')} "
                f"expected {band}/{reason}"
            )
        if score.get("method") != "rules" or score.get("llm") is not None:
            raise SystemExit(f"FAIL {rid} must stay on the rules path")
        return row

    primary_row = need(fresh["id"], "auto_brief", "auto_primary")
    if primary_row["status_in_pool"] != "active" or primary_row["drop_reason"] is not None:
        raise SystemExit("FAIL: auto_brief must stay active")
    practice_row = need(practice["id"], "review", "review_practice")
    if practice_row["status_in_pool"] != "active":
        raise SystemExit("FAIL: practice review must stay active")
    dropped = need(stale["id"], "drop", "drop_low_score")
    if dropped["status_in_pool"] != "dropped" or dropped["drop_reason"] != "low_score":
        raise SystemExit("FAIL: low score must drop with low_score")
    if "score:low_score" not in (dropped.get("notes") or ""):
        raise SystemExit(f"FAIL: low_score notes missing trace: {dropped.get('notes')!r}")
    kept_skip = by_id[skipped["id"]]
    if "score" in kept_skip or kept_skip["drop_reason"] != "editor_skip" or kept_skip["notes"] != "editor said skip":
        raise SystemExit("FAIL: editor_skip was rewritten")
    kept_promoted = by_id[promoted["id"]]
    if "score" in kept_promoted or kept_promoted["status_in_pool"] != "promoted":
        raise SystemExit("FAIL: promoted row was rewritten")
    held = need(deferred["id"], "review", "review_deferred")
    if held["status_in_pool"] != "deferred" or held["drop_reason"] is not None:
        raise SystemExit("FAIL: deferred row must not become an auto brief or a drop when it still clears review")
    need(no_primary["id"], "review", "review_no_primary")
    kept_blocked = by_id[blocked["id"]]
    if "score" in kept_blocked or kept_blocked["drop_reason"] != "prefilter_block":
        raise SystemExit("FAIL: gate drop was rescored into a new reason")
    solo_c = by_id[solo["id"]]["score"]["components"]["corroboration"]
    pair_c = by_id[pair_report["id"]]["score"]["components"]["corroboration"]
    if not pair_c > solo_c:
        raise SystemExit(f"FAIL: cluster primary should raise corroboration {pair_c} vs {solo_c}")
    if not by_id[viral["id"]]["score"]["components"]["velocity"] > by_id[quiet["id"]]["score"]["components"]["velocity"]:
        raise SystemExit("FAIL: bookmark velocity did not rank the faster post higher")
    if not by_id[steps["id"]]["score"]["components"]["actionability"] > by_id[plain["id"]]["score"]["components"]["actionability"]:
        raise SystemExit("FAIL: step/repo heuristic did not move actionability")
    if not by_id[steps["id"]]["score"]["value"] > by_id[plain["id"]]["score"]["value"]:
        raise SystemExit("FAIL: actionability did not raise the score")

    noisy = score_records(
        [
            fresh,
            _fixture(
                id="cand-20261014-bbbbbbbbbbb1",
                url="https://x.com/openai/status/11",
                channel="x",
                handle="openai-blog",
                status="dropped",
                drop_reason="prefilter_block",
                prefilter="BLOCK",
                notes="gate",
                cluster_id="clu-scorenoise001",
            ),
            _fixture(
                id="cand-20261014-bbbbbbbbbbb2",
                url="https://x.com/openai/status/12",
                channel="x",
                handle="openai-blog",
                status="dropped",
                drop_reason="editor_skip",
                prefilter="PASS",
                notes="skip",
                cluster_id="clu-scorenoise002",
            ),
            _fixture(
                id="cand-20261014-bbbbbbbbbbb3",
                url="https://x.com/openai/status/13",
                channel="x",
                handle="openai-blog",
                status="dropped",
                drop_reason="no_new_info",
                prefilter="PASS",
                notes="old",
                cluster_id="clu-scorenoise003",
            ),
        ],
        options,
        cfg,
        as_of,
    )
    clean_prior = primary_row["score"]["components"]["prior"]
    noisy_prior = next(row for row in noisy if row["id"] == fresh["id"])["score"]["components"]["prior"]
    if not noisy_prior < clean_prior:
        raise SystemExit(f"FAIL: discarded posts did not lower prior {noisy_prior} vs {clean_prior}")

    rumor = _fixture(
        id="cand-20261014-cccccccccc01",
        url="https://x.com/rando/status/1",
        channel="x",
        handle="rando",
        snippet="FIXTURE GPT-5.5 is out and secretly worse, trust me https://openai.com/blog/fixture-score-pair",
        cluster_id="clu-scorepair0001",
        engagement={"likes": 50, "bookmarks": 200, "captured_at": "2026-10-14T11:00:00Z"},
    )
    lab_x = _fixture(
        id="cand-20261014-cccccccccc02",
        url="https://x.com/OpenAI/status/2",
        channel="x",
        handle="OpenAI",
        role_guess="primary",
        tier_prior="T1",
        title="FIXTURE model release on X",
        snippet="FIXTURE model release on X.",
        cluster_id="clu-scorelabx0001",
    )
    neighbours = {
        row["id"]: row
        for row in score_records([pair_primary, rumor, lab_x], options, cfg, as_of)
    }
    if neighbours[pair_primary["id"]]["score"]["band"] != "auto_brief":
        raise SystemExit("FAIL: the official RSS row should still reach auto_brief")
    for rid in (rumor["id"], lab_x["id"]):
        got = neighbours[rid]["score"]
        if got["band"] == "auto_brief" or got["band_reason"] not in {"review_not_official", "review_score"}:
            raise SystemExit(f"FAIL: {rid} must not auto-publish: {got['band']}/{got['band_reason']}")
        if got["official_source"]:
            raise SystemExit(f"FAIL: {rid} is not an official RSS row")

    timing_drops = [
        _fixture(
            id=f"cand-20261014-dddddddddd0{n}",
            url=f"https://openai.com/blog/fixture-timing-{n}",
            handle="openai-blog",
            role_guess="primary",
            tier_prior="T1",
            status="dropped",
            drop_reason=reason,
            notes="machine",
            cluster_id=f"clu-scoretiming{n:02d}",
        )
        for n, reason in enumerate(("low_score", "duplicate_url", "no_new_info", "stale_old"), start=1)
    ]
    alone_prior = score_records([fresh], options, cfg, as_of)[0]["score"]["components"]["prior"]
    timed = next(row for row in score_records([fresh] + timing_drops, options, cfg, as_of) if row["id"] == fresh["id"])
    if timed["score"]["components"]["prior"] != alone_prior:
        raise SystemExit("FAIL: decay and duplicate drops must not lower the source prior")
    briefed = dict(fresh, id="cand-20261014-eeeeeeeeee01", brief_id="brf-20261014-eeeeeeeeee01", cluster_id="clu-scorebrief001")
    boosted = next(row for row in score_records([fresh, briefed], options, cfg, as_of) if row["id"] == fresh["id"])
    if not boosted["score"]["components"]["prior"] > alone_prior:
        raise SystemExit("FAIL: a published brief must count as a hit")
    late = parse_utc("2026-10-20T12:00:00Z")
    kept_brief = next(row for row in score_records([briefed], options, cfg, late))
    if "score" in kept_brief or kept_brief["status_in_pool"] != "active":
        raise SystemExit("FAIL: a published brief must not be rescored or dropped by decay")
    future = dict(plain, id="cand-20261014-eeeeeeeeee02", published_at="2026-10-20T00:00:00Z", cluster_id="clu-scorefuture01")
    if score_records([future], options, cfg, as_of)[0]["score"]["components"]["decay"] != 0.55:
        raise SystemExit("FAIL: a future clock must read as unreliable, not fresh")
    odd = dict(viral, id="cand-20261014-eeeeeeeeee03", engagement={"likes": -5, "bookmarks": "abc"})
    score_records([viral, odd], options, cfg, as_of)
    old_row = dict(fresh, id="cand-20261001-eeeeeeeeee04", ingested_at="2026-10-01T00:00:00Z", cluster_id="clu-scoreold00001")
    if "score" in score_records([old_row], options, cfg, as_of)[0]:
        raise SystemExit("FAIL: rows outside score_window_days must keep their last score")
    try:
        ScoreConfig(bookmark_prior=0).validate()
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: bookmark_prior=0 must be rejected")

    for row in first + list(neighbours.values()):
        errors = sorted(validator.iter_errors(row), key=lambda err: list(err.path))
        if errors:
            loc = "/".join(str(part) for part in errors[0].path) or "(root)"
            raise SystemExit(f"FAIL schema {row['id']} {loc}: {errors[0].message}")

    bare = json.loads(dumps_record(dropped))
    bare["notes"] = ""
    if not list(validator.iter_errors(bare)):
        raise SystemExit("FAIL: low_score without notes must fail schema")

    import tempfile

    review_text = review_markdown(first, as_of)
    if practice["id"] not in review_text or "https://x.com/op7418/status/501" not in review_text:
        raise SystemExit("FAIL: review list missed the practice row")
    if "pip install fixture-tool" in review_text or "github.com/example/fixture-tool" in review_text:
        raise SystemExit("FAIL: review list copied the post body")
    if fresh["id"] in review_text:
        raise SystemExit("FAIL: auto_brief row leaked into the review list")

    with tempfile.TemporaryDirectory() as tmp:
        pool = Path(tmp) / "ai-radar-pool"
        from ingest_x import merge_pool

        merge_pool(pool, [fresh, practice, stale], "2026-10-14T11:00:00Z")
        pairs = read_pool(pool)
        scored, code = run_score(
            [row for _path, row in pairs],
            as_of,
            cfg,
            options,
            None,
            pairs,
            pool,
            True,
        )
        if code != 0:
            raise SystemExit(f"FAIL: pool score exit {code}")
        day = pool / "candidates" / "2026-10-14.jsonl"
        again_pairs = read_pool(pool)
        before = day.read_bytes()
        run_score(
            [row for _path, row in again_pairs],
            as_of,
            cfg,
            options,
            None,
            again_pairs,
            pool,
            True,
        )
        if day.read_bytes() != before:
            raise SystemExit("FAIL: rescore changed pool bytes")
        review = pool / "review" / "2026-10-14.md"
        if not review.is_file() or practice["id"] not in review.read_text(encoding="utf-8"):
            raise SystemExit("FAIL: review file missing")
        if any(row["status_in_pool"] == "dropped" and row["drop_reason"] == "low_score" and not row["notes"] for row in scored):
            raise SystemExit("FAIL: pool low_score row has empty notes")

    public_out = ROOT / "public" / "_score_should_not_write.jsonl"
    try:
        write_batch(public_out, first[:1])
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: score wrote under public/")
    if public_out.exists():
        public_out.unlink()
        raise SystemExit("FAIL: public jsonl was created")
    print("OK score_pool self-check")


def _load_input(path: Path | None) -> list[dict]:
    raw = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    if not raw.strip():
        raise IngestError("empty score input")
    if path and path.suffix == ".jsonl" or (path is None and raw.lstrip().startswith("{")):
        rows = []
        for line_no, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IngestError(f"line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise IngestError(f"line {line_no}: expected an object")
            rows.append(row)
        if rows:
            return rows
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IngestError(f"score input: {exc}") from exc
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise IngestError("score input must be JSONL or a list")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score annotated candidate rows. Rules only; no network LLM.")
    parser.add_argument("--input", "-i", help="JSONL or JSON records. Not combined with --pool-dir.")
    parser.add_argument("--out", help="Overwrite this JSONL. Refuses public/.")
    parser.add_argument("--pool-dir", help="Private pool root. Rewrites candidates/*.jsonl in place.")
    parser.add_argument("--as-of", help="ISO-8601 UTC clock for decay. Default: now.")
    parser.add_argument("--write-review", action="store_true", help="Write review/YYYY-MM-DD.md inside --pool-dir.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if args.pool_dir and args.input:
        parser.error("pass --input or --pool-dir, not both")
    if not args.pool_dir and not args.out:
        parser.error("pass --out and/or --pool-dir")
    try:
        cfg = load_score_config(ROOT)
        as_of = parse_utc(args.as_of) if args.as_of else parse_utc(utc_now_iso())
        options = options_from_repo(as_of)
        pool_dir = Path(args.pool_dir) if args.pool_dir else None
        pairs = None
        if pool_dir is not None:
            assert_shift_pool_dir(pool_dir)
            pairs = read_pool(pool_dir)
            rows = [row for _path, row in pairs]
        else:
            rows = _load_input(Path(args.input) if args.input else None)
        run_score(
            rows,
            as_of,
            cfg,
            options,
            Path(args.out) if args.out else None,
            pairs,
            pool_dir,
            args.write_review,
        )
        return 0
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
