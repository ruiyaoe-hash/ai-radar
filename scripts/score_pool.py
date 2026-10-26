#!/usr/bin/env python3
"""Score candidate rows after annotate gates and before promotion.

v1 (control), still the production band unless config score.active_scorer is v2:

  value ≈ prior(tier, smoothed editor hit rate)
        × exp(-age_hours / τ)
        × corroboration(independent evidence, not reprint drops)
        × velocity(bookmark/like vs author baseline)
        + actionability (capped rule heuristic)

v2 is written under score.v2 when score.shadow_v2 is true. It does not change
band while active_scorer stays v1.

Bands written onto the row:
  auto_brief  high v1 score, the row itself comes from an official source on an
              AUTO_CHANNELS feed (not X, not a cluster neighbour), and not practice.
              Forced P0 never uses this band.
  review      mid/high, practice, deferred, cluster-only primary, no primary,
              or review_p0 (forced P0, human queue, no archive write)
  drop        low score on an active row → status dropped, drop_reason low_score.
              A deferred row is an edition hold and is not rewritten into low_score.

Hit rate counts editor promotions (status promoted) only. A plain auto_brief
(brief_id with no promotion) is not user-value feedback. Only editorial or
quality drops (QUALITY_DROPS) are misses. Reprint drops do not count as
independent evidence. Rows that already carry brief_id are a publish decision
and are not rescored. editor_skip, promoted, and rerouted rows are left
untouched. Only rows ingested within score_window_days are rescored, except
that a low_score or stale_old row inside the window can be lifted when Forced
P0 matches.

Rules scoring does not call a network. AI_RADAR_SCORE_LLM_URL only fills
score.llm.skipped_reason; there is no hosted adapter in this repo.
card_copy sits beside score: a short reason, an evidence label, a suggested
action, and a high-priority review flag. The sentences do not contain scores.

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
        canonical_url,
        evidence_links,
        has_primary_ref,
        options_from_repo,
        read_pool,
        url_is_primary,
        write_pool,
    )
    from card_copy import build_card_copy
    from force_p0 import (
        REPRINT_DROP_REASONS,
        assign_p0,
        hook_document,
        match_multi_a_tier,
        match_row_p0,
        merge_p0,
    )
    from score_pool_v2 import resolve_v2_config, score_v2
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
        canonical_url,
        evidence_links,
        has_primary_ref,
        options_from_repo,
        read_pool,
        url_is_primary,
        write_pool,
    )
    from .card_copy import build_card_copy
    from .force_p0 import (
        REPRINT_DROP_REASONS,
        assign_p0,
        hook_document,
        match_multi_a_tier,
        match_row_p0,
        merge_p0,
    )
    from .score_pool_v2 import resolve_v2_config, score_v2
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
    active_scorer: str = "v1"
    shadow_v2: bool = True
    v2: dict | None = None

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
        if self.active_scorer not in {"v1", "v2"}:
            raise IngestError("score.active_scorer must be v1 or v2")
        if not isinstance(self.shadow_v2, bool):
            raise IngestError("score.shadow_v2 must be a boolean")
        self.v2 = resolve_v2_config(self.v2 if isinstance(self.v2, dict) else None)


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
    """Editor promotions are hits. A plain auto_brief publish is not.

    brief_id means the machine published an L2 brief. That is not an explicit
    editor outcome, so it does not raise the account's hit rate. Editorial or
    quality drops (QUALITY_DROPS) are misses. low_score, duplicate_*, no_new_info,
    stale_old, and missing clocks stay out of the denominator. The same id counts once.
    """
    hits: dict[str, set[str]] = defaultdict(set)
    drops: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        handle = handle_of(row)
        if not handle:
            continue
        rid = str(row.get("id") or "")
        status = row.get("status_in_pool")
        if status == "promoted":
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
    # Edition hold is not a value judgment. Do not collapse deferred into low_score.
    if status == "deferred":
        return "review", "review_deferred"
    if value < cfg.review_min:
        return "drop", "drop_low_score"
    if practice:
        return "review", "review_practice"
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


def counts_spread(row: dict) -> bool:
    """Reach: accounts that passed the gate, including homologous reprints."""
    if row.get("prefilter") != "PASS":
        return False
    if row.get("status_in_pool") == "dropped" and row.get("drop_reason") in QUALITY_DROPS:
        return False
    return True


def counts_independent(row: dict) -> bool:
    """Independent witnesses. Reprint drops and folded no-progress rows do not count."""
    if not counts_spread(row):
        return False
    if row.get("status_in_pool") == "dropped" and row.get("drop_reason") in REPRINT_DROP_REASONS:
        return False
    notes = str(row.get("notes") or "")
    if row.get("status_in_pool") == "deferred" and "no_new_info" in notes:
        return False
    return True


def primary_urls(row: dict, options) -> set[str]:
    found: set[str] = set()
    own = canonical_url(row.get("url_norm") or row.get("url"))
    if own and url_is_primary(own, options):
        found.add(own)
    for link in evidence_links(row):
        if url_is_primary(link, options):
            found.add(link)
    return found


def corroboration_value(independent_sources: int, evidence_n: int, primary: bool) -> float:
    """Boost from distinct primary URLs when we have them, else from independent accounts.

    Homologous reprints that share one official URL do not add extras.
    """
    if evidence_n > 0:
        extras = min(3, max(0, evidence_n - 1))
    else:
        extras = min(3, max(0, independent_sources - 1))
    return _r4(min(1.0, 0.72 + extras * 0.08 + (0.16 if primary else 0.0)))


def source_reliability_of(row: dict, hit: float, cfg: ScoreConfig) -> float:
    """Tier prior blended with editor hit rate. role_guess is not mixed in."""
    tier = row.get("tier_prior")
    tier_w = TIER_WEIGHT.get(tier, UNKNOWN_TIER) if isinstance(tier, str) else UNKNOWN_TIER
    return _r4(cfg.tier_mix * tier_w + (1.0 - cfg.tier_mix) * hit)


def evidence_grade_of(row: dict) -> float:
    role = (row.get("source") or {}).get("role_guess")
    if isinstance(role, str) and role in ROLE_WEIGHT:
        return ROLE_WEIGHT[role]
    return 0.5


def edition_eligibility_of(row: dict, as_of: datetime, stale_hours: float) -> str:
    notes = str(row.get("notes") or "")
    if (
        row.get("status_in_pool") == "deferred"
        or "rss_backfill_not_today" in notes
        or "stale_window" in notes
        or "edition_date" in notes
    ):
        return "held_edition"
    age = age_hours(row, as_of)
    if age is not None and age > stale_hours:
        return "stale_window"
    return "eligible"


def shanghai_day_of(row: dict) -> str | None:
    for key in ("published_at", "ingested_at"):
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            try:
                return shanghai_file_day(raw)
            except IngestError:
                continue
    return None


def score_eligible(row: dict, as_of: datetime, cfg: ScoreConfig) -> bool:
    if not in_score_window(row, as_of, cfg.score_window_days):
        return False
    if scorable(row):
        return True
    if (
        row.get("status_in_pool") == "dropped"
        and row.get("drop_reason") in {"low_score", "stale_old"}
        and row.get("prefilter") == "PASS"
        and match_row_p0(row)
    ):
        return True
    return False


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
    primary_cluster: set[str] = set()
    spread_ids: dict[str, set[str]] = defaultdict(set)
    independent_ids: dict[str, set[str]] = defaultdict(set)
    evidence_urls: dict[str, set[str]] = defaultdict(set)
    ratios: dict[str, list[float]] = defaultdict(list)
    rates: dict[str, list[float]] = defaultdict(list)
    ages = [age_hours(row, as_of) for row in copied]
    for row, age in zip(copied, ages):
        key = cluster_key(row)
        if counts_spread(row):
            spread_ids[key].add(source_identity(row))
        if counts_independent(row):
            independent_ids[key].add(source_identity(row))
            evidence_urls[key].update(primary_urls(row, options))
            if row_is_primary(row, options):
                primary_cluster.add(key)
        if not _pass_row(row):
            continue
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
    v2cfg = cfg.v2 if isinstance(cfg.v2, dict) else resolve_v2_config(None)
    stale_hours = float(getattr(options, "stale_hours", 48.0) or 48.0)
    pending: list[tuple[dict, dict]] = []
    for row, age in zip(copied, ages):
        if not score_eligible(row, as_of, cfg):
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
        reliability = source_reliability_of(row, hit, cfg)
        grade = _r4(evidence_grade_of(row))
        decay = _r4(decay_of(row, as_of, cfg.tau_hours))
        key = cluster_key(row)
        members = set(independent_ids.get(key, set()))
        members.add(source_identity(row))
        evidence_n = len(evidence_urls.get(key, set()))
        spread_n = len(spread_ids.get(key) or {source_identity(row)})
        primary = key in primary_cluster or row_is_primary(row, options)
        corroboration = corroboration_value(len(members), evidence_n, primary)
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
        would_band, would_reason = band_of(value, primary, practice, status, cfg, official)
        pending.append(
            (
                row,
                {
                    "prior": prior,
                    "reliability": reliability,
                    "grade": grade,
                    "decay": decay,
                    "corroboration": corroboration,
                    "velocity": velocity,
                    "act": act,
                    "value": value,
                    "practice": practice,
                    "official": official,
                    "primary": primary,
                    "would_band": would_band,
                    "would_reason": would_reason,
                    "edition": edition_eligibility_of(row, as_of, stale_hours),
                    "age": age,
                    "evidence_n": evidence_n,
                    "spread_n": spread_n,
                    "independent_n": len(members),
                },
            )
        )

    would_be = {str(row.get("id")): (meta["would_band"], meta["would_reason"]) for row, meta in pending}
    multi = match_multi_a_tier(copied, would_be, set(getattr(options, "a_tier", set()) or set()), shanghai_day_of)
    for row, meta in pending:
        spec = merge_p0(match_row_p0(row), multi.get(str(row.get("id"))))
        band, reason = meta["would_band"], meta["would_reason"]
        scorer_name = "v1"
        forced = spec is not None
        if forced:
            bypassed: list[str] = []
            if meta["value"] < cfg.review_min:
                bypassed.append("low_score")
            if str(row.get("status_in_pool") or "") == "deferred" or meta["edition"] == "held_edition":
                bypassed.append("edition_date")
            if row.get("drop_reason") in {"low_score", "stale_old"}:
                bypassed.append(str(row.get("drop_reason")))
            assign_p0(row, spec, bypassed)
            band, reason = "review", "review_p0"
            if row.get("status_in_pool") == "dropped" and row.get("drop_reason") in {"low_score", "stale_old"}:
                row["status_in_pool"] = "active"
                row["drop_reason"] = None
                row["archive_id"] = None
                row["promotion_path"] = None
            elif row.get("status_in_pool") == "deferred":
                row["status_in_pool"] = "active"
                row["drop_reason"] = None
        v2 = None
        if cfg.shadow_v2 or cfg.active_scorer == "v2" or forced:
            v2 = score_v2(
                row,
                age_hours=meta["age"],
                source_reliability=meta["reliability"],
                evidence_grade=meta["grade"],
                independent_sources=meta["independent_n"],
                evidence_n=meta["evidence_n"],
                spread_n=meta["spread_n"],
                primary=meta["primary"],
                official=meta["official"],
                practice=meta["practice"],
                actionability_raw=meta["act"],
                actionability_cap=cfg.actionability_cap,
                status=str(row.get("status_in_pool") or ""),
                cfg=v2cfg,
                forced=forced,
            )
            if llm and v2 is not None:
                v2["llm"] = {"skipped_reason": llm.get("skipped_reason") or "adapter_not_configured"}
            if cfg.active_scorer == "v2" and not forced and v2 is not None:
                band, reason = v2["band"], v2["band_reason"]
                scorer_name = "v2"
        value = meta["value"]
        prior = meta["prior"]
        decay = meta["decay"]
        corroboration = meta["corroboration"]
        velocity = meta["velocity"]
        act = meta["act"]
        row["score"] = {
            "value": value,
            "band": band,
            "band_reason": reason,
            "primary_source": bool(meta["primary"]),
            "official_source": bool(meta["official"]),
            "method": "rules",
            "scorer": scorer_name,
            "source_reliability": meta["reliability"],
            "evidence_grade": meta["grade"],
            "content_value": value,
            "edition_eligibility": meta["edition"],
            "components": {
                "prior": prior,
                "decay": decay,
                "corroboration": corroboration,
                "velocity": velocity,
                "actionability": act,
                "spread": meta["spread_n"],
                "independent_evidence": meta["evidence_n"],
            },
            "llm": llm,
        }
        if v2 is not None:
            row["score"]["v2"] = v2
        row["card_copy"] = build_card_copy(
            row,
            official=bool(meta["official"]),
            independent_n=meta["independent_n"],
            band=band,
            band_reason=reason,
            edition=meta["edition"],
        )
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
    """Human queue. No raw post body. Qualifying practice cards are written later by the shift."""
    day = shanghai_file_day(as_of.strftime("%Y-%m-%dT%H:%M:%SZ"))
    queued = []
    for row in rows:
        score = row.get("score") or {}
        if score.get("band") != "review":
            continue
        if row.get("status_in_pool") == "dropped":
            continue
        queued.append(row)
    def _queue_key(row: dict) -> tuple:
        spec = row.get("force_p0") or {}
        p0 = 1 if spec.get("active") else 0
        promote = 1 if spec.get("default_action") == "promote" else 0
        return (-p0, -promote, -(row.get("score") or {}).get("value", 0), str(row.get("id")))

    queued.sort(key=_queue_key)
    lines = [
        f"# 审核清单 {day}",
        "",
        "机器低分已是 `dropped` + `low_score`，不在本清单。延后（deferred，今日档先不上）也不是低价值，原因仍是 `review_deferred`。",
        "带 `review_p0` 的行是强制 P0（Forced P0）。代码是准绳，例程可以再看一眼。它们排在最前，只等人决定晋升或跳过，脚本不写公开归档，也不写今日必看。",
        "同一行的 `card_copy` 是给卡片用的短句：为什么值得看、证据标签、建议动作。短句里没有分数。`high_priority_review` 只表示优先审，不是已经公开。",
        "实操仍留在这张清单里。过了步骤和收藏两道门的，由班次里的 project_public_lanes 写入 practice inbox，verified 保持 false。",
        "通过并上 L1：池行改为 `promoted`，`archive_id` 指向公开卡，公开卡写同一个 `candidate_id`。",
        "否决：`drop_reason=editor_skip`，并且 `notes` 不能空。`annotate_gates` 和 `score_pool` 都不再改这一行。",
        "私人 action（tried / ignored）写未跟踪的 `owner-actions.local.json`，或飞书。不要写入公开 `public/owner-actions.json`。",
        "同目录的 `p0-日期.json` 是通知钩子，没有正文。飞书仍只推已经由人写进归档的正式 P0。",
        "",
        "| cid | band | value | handle | lane | primary | p0 | default | 证据 | 动作 | url |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in queued:
        score = row["score"]
        handle = handle_of(row) or ""
        if row.get("lane_hint") == "practice" or row.get("tier_prior") == "practice" or score.get("band_reason") == "review_practice":
            lane = "practice"
        else:
            lane = row.get("lane_hint") or "digest"
        spec = row.get("force_p0") or {}
        copy = row.get("card_copy") or {}
        kinds = ",".join(spec.get("kinds") or []) if spec.get("active") else ""
        lines.append(
            "| {cid} | {band} | {value:.4f} | {handle} | {lane} | {primary} | {p0} | {default} | {evidence} | {action} | {url} |".format(
                cid=row.get("id"),
                band=score.get("band_reason"),
                value=float(score.get("value") or 0),
                handle=handle,
                lane=lane,
                primary="yes" if score.get("primary_source") else "no",
                p0=kinds,
                default=spec.get("default_action") or "",
                evidence=copy.get("evidence_label") or "",
                action=copy.get("suggested_action") or "",
                url=row.get("url_norm") or row.get("url") or "",
            )
        )
    if not queued:
        lines.append("|  |  |  |  |  |  |  |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def write_review(pool_dir: Path, rows: list[dict], as_of: datetime) -> Path:
    assert_shift_pool_dir(pool_dir)
    day = shanghai_file_day(as_of.strftime("%Y-%m-%dT%H:%M:%SZ"))
    path = pool_dir / "review" / f"{day}.md"
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(review_markdown(rows, as_of), encoding="utf-8")
    hook_path = pool_dir / "review" / f"p0-{day}.json"
    assert_not_public(hook_path)
    hook_path.write_text(
        json.dumps(hook_document(rows, day), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
    primary_copy = primary_row.get("card_copy") or {}
    if (
        primary_copy.get("evidence_label") != "官方原始信息"
        or primary_copy.get("suggested_action") != "持续观察"
        or primary_copy.get("high_priority_review")
        or primary_copy.get("watch_reason") != "官方源发布了新说明。"
        or "card_copy" in (primary_row.get("score") or {})
    ):
        raise SystemExit(f"FAIL: official auto card copy {primary_copy}")
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
    held_copy = held.get("card_copy") or {}
    if (
        held_copy.get("suggested_action") != "暂缓"
        or held_copy.get("high_priority_review")
        or held_copy.get("evidence_label") != "官方原始信息"
    ):
        raise SystemExit(f"FAIL: edition hold copy {held_copy}")
    need(no_primary["id"], "review", "review_no_primary")
    kept_blocked = by_id[blocked["id"]]
    if "score" in kept_blocked or kept_blocked["drop_reason"] != "prefilter_block":
        raise SystemExit("FAIL: gate drop was rescored into a new reason")
    solo_c = by_id[solo["id"]]["score"]["components"]["corroboration"]
    pair_c = by_id[pair_report["id"]]["score"]["components"]["corroboration"]
    if not pair_c > solo_c:
        raise SystemExit(f"FAIL: cluster primary should raise corroboration {pair_c} vs {solo_c}")
    if by_id[fresh["id"]]["score"].get("scorer") != "v1" or "v2" not in by_id[fresh["id"]]["score"]:
        raise SystemExit("FAIL: production default must keep v1 band and shadow v2")
    if by_id[fresh["id"]]["score"]["v2"]["method"] != "rules":
        raise SystemExit("FAIL: v2 must stay on the rules path")
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
    with_brief = next(row for row in score_records([fresh, briefed], options, cfg, as_of) if row["id"] == fresh["id"])
    if with_brief["score"]["components"]["prior"] != alone_prior:
        raise SystemExit(
            "FAIL: a published auto_brief must not raise source prior "
            f"({with_brief['score']['components']['prior']} vs {alone_prior})"
        )
    promoted_hit = dict(fresh)
    promoted_hit["id"] = "cand-20261014-eeeeeeeeee05"
    promoted_hit["status_in_pool"] = "promoted"
    promoted_hit["archive_id"] = "evt-20261014-fixture-hit"
    promoted_hit["promotion_path"] = "normal"
    promoted_hit["notes"] = "editor promoted"
    promoted_hit["cluster_id"] = "clu-scorehit0001"
    with_promote = next(row for row in score_records([fresh, promoted_hit], options, cfg, as_of) if row["id"] == fresh["id"])
    if not with_promote["score"]["components"]["prior"] > alone_prior:
        raise SystemExit("FAIL: an editor promotion must raise source prior")
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

    solo_alone = score_records([solo], options, cfg, as_of)[0]
    reprint = _fixture(
        id="cand-20261014-ffffffffffff",
        url="https://www.theverge.com/2026/10/14/fixture-reprint",
        handle="theverge-ai",
        role_guess="report",
        tier_prior="T3",
        status="dropped",
        drop_reason="no_new_info",
        notes="gate: no_new_info",
        snippet="FIXTURE model rumor from one desk. reprint",
        cluster_id=solo["cluster_id"],
    )
    solo_re = next(row for row in score_records([solo, reprint], options, cfg, as_of) if row["id"] == solo["id"])
    if solo_re["score"]["components"]["corroboration"] != solo_alone["score"]["components"]["corroboration"]:
        raise SystemExit("FAIL: no_new_info reprint must not raise corroboration")
    if solo_re["score"]["components"]["independent_evidence"] != solo_alone["score"]["components"]["independent_evidence"]:
        raise SystemExit("FAIL: reprint must not raise independent evidence")
    if not solo_re["score"]["components"]["spread"] > solo_alone["score"]["components"]["spread"]:
        raise SystemExit(
            "FAIL: reprint should still count as spread "
            f"{solo_re['score']['components']['spread']} vs {solo_alone['score']['components']['spread']}"
        )
    cite_a = _fixture(
        id="cand-20261014-eeeeeeeeee11",
        url="https://techcrunch.com/2026/10/14/fixture-cite-a",
        handle="techcrunch-ai",
        role_guess="report",
        tier_prior="T3",
        snippet="FIXTURE recap of https://openai.com/blog/fixture-same-primary",
        cluster_id="clu-scorecite0001",
    )
    cite_b = _fixture(
        id="cand-20261014-eeeeeeeeee12",
        url="https://www.theverge.com/2026/10/14/fixture-cite-b",
        handle="theverge-ai",
        role_guess="report",
        tier_prior="T3",
        snippet="FIXTURE same recap of https://openai.com/blog/fixture-same-primary",
        cluster_id="clu-scorecite0001",
    )
    cited = {row["id"]: row for row in score_records([cite_a, cite_b], options, cfg, as_of)}
    if cited[cite_a["id"]]["score"]["components"]["independent_evidence"] != 1:
        raise SystemExit(
            "FAIL: homologous reprints must share one evidence URL, got "
            f"{cited[cite_a['id']]['score']['components']['independent_evidence']}"
        )
    masked = _fixture(
        id="cand-20261014-eeeeeeeeee13",
        url="https://x.com/OpenAI/status/77",
        channel="x",
        handle="OpenAI",
        role_guess="report",
        tier_prior="T1",
        snippet="FIXTURE second-hand recap without a primary link.",
        cluster_id="clu-scoremask0001",
    )
    masked_row = score_records([masked], options, cfg, as_of)[0]
    if masked_row["score"]["evidence_grade"] != ROLE_WEIGHT["report"]:
        raise SystemExit(f"FAIL: report evidence grade masked: {masked_row['score']['evidence_grade']}")
    if not masked_row["score"]["source_reliability"] > masked_row["score"]["evidence_grade"]:
        raise SystemExit("FAIL: source reliability should stay the account prior, separate from evidence grade")
    if masked_row["score"]["v2"]["confidence"] > 0.48:
        raise SystemExit(f"FAIL: second-hand report confidence must stay capped: {masked_row['score']['v2']['confidence']}")
    if masked_row["score"]["band"] == "auto_brief":
        raise SystemExit("FAIL: a report role must not auto-publish")

    held_low = _fixture(
        id="cand-20261014-111111111101",
        url="https://example.com/fixture-held-low",
        channel="web",
        handle="randomperson",
        published_at="2026-10-01T00:00:00Z",
        status="deferred",
        snippet="FIXTURE old note held for the next edition.",
        cluster_id="clu-scoreheldlow1",
        notes="gate: deferred stale_window>48h",
    )
    held_row = score_records([held_low], options, cfg, as_of)[0]
    if held_row["status_in_pool"] != "deferred" or held_row["drop_reason"] is not None:
        raise SystemExit(f"FAIL: edition hold became {held_row['status_in_pool']} {held_row['drop_reason']}")
    if held_row["score"]["band_reason"] != "review_deferred" or held_row["score"]["edition_eligibility"] != "held_edition":
        raise SystemExit(
            f"FAIL: edition hold reason {held_row['score']['band_reason']} {held_row['score'].get('edition_eligibility')}"
        )
    if held_row["score"]["value"] >= cfg.review_min:
        raise SystemExit("FAIL: held-low fixture was not actually below the review threshold")

    p0_payload = json.loads((ROOT / "testdata" / "p0" / "cases.json").read_text(encoding="utf-8"))
    p0_as_of = parse_utc(p0_payload["as_of"])
    p0_rows = []
    for case in p0_payload["cases"]:
        raw_rows = case.get("rows") or [case["row"]]
        scored_case = {row["id"]: row for row in score_records(raw_rows, options, cfg, p0_as_of)}
        p0_rows.extend(scored_case.values())
        for raw in raw_rows:
            got = scored_case[raw["id"]]
            score = got.get("score") or {}
            if score.get("band") != "review" or score.get("band_reason") != "review_p0":
                raise SystemExit(
                    f"FAIL {case['name']} {raw['id']} band {score.get('band')}/{score.get('band_reason')} "
                    f"value={score.get('value')}"
                )
            if score.get("band") == "auto_brief" or got.get("status_in_pool") != "active":
                raise SystemExit(
                    f"FAIL {case['name']}: P0 must stay active for review, got {got.get('status_in_pool')}"
                )
            kinds = (got.get("force_p0") or {}).get("kinds") or []
            for kind in case.get("expect_kinds") or []:
                if kind not in kinds:
                    raise SystemExit(f"FAIL {case['name']}: missing kind {kind} in {kinds}")
            expect_default = case.get("expect_default")
            if expect_default and (got.get("force_p0") or {}).get("default_action") != expect_default:
                raise SystemExit(
                    f"FAIL {case['name']}: default {(got.get('force_p0') or {}).get('default_action')} != {expect_default}"
                )
            if "low_score" not in ((got.get("force_p0") or {}).get("bypassed") or []):
                if score.get("value", 1) < cfg.review_min:
                    raise SystemExit(f"FAIL {case['name']}: low score was not bypassed")
            copy = got.get("card_copy") or {}
            reason_text = str(copy.get("watch_reason") or "")
            if not copy.get("high_priority_review") or any(ch.isdigit() for ch in reason_text):
                raise SystemExit(f"FAIL {case['name']}: card copy {copy}")
            if case["name"] == "claude-duet-research-preview" and (
                copy.get("suggested_action") != "持续观察" or copy.get("evidence_label") != "尚待核实"
            ):
                raise SystemExit(f"FAIL {case['name']}: preview must stay a watch, got {copy}")
            if case["name"] == "php2shell-upgrade" and copy.get("suggested_action") != "立即行动":
                raise SystemExit(f"FAIL {case['name']}: upgrade copy {copy}")
            if case["name"] == "two-a-tier-same-day" and (
                copy.get("suggested_action") != "立即行动" or copy.get("evidence_label") != "多源确认"
            ):
                raise SystemExit(f"FAIL {case['name']}: tool-choice copy {copy}")

    lone = _fixture(
        id="cand-20261022-aaaaaaaaaa21",
        url="https://x.com/karpathy/status/88001",
        channel="x",
        handle="karpathy",
        tier_prior="a_tier",
        published_at="2026-10-22T09:00:00Z",
        ingested_at="2026-10-22T09:30:00Z",
        snippet="FIXTURE a single a_tier note about a paper.",
        cluster_id="clu-scorelonea01",
    )
    lone["ingested_at"] = "2026-10-22T09:30:00Z"
    lone_row = score_records([lone], options, cfg, p0_as_of)[0]
    if lone_row["score"]["band_reason"] == "review_p0" or lone_row.get("force_p0"):
        raise SystemExit("FAIL: one a_tier account must not force P0")

    if cfg.active_scorer != "v1" or cfg.shadow_v2 is not True:
        raise SystemExit("FAIL: config default must stay v1 with v2 in shadow")
    flipped = ScoreConfig(**{**cfg.__dict__})
    flipped.active_scorer = "v2"
    flipped.validate()
    flipped_p0 = score_records([p0_payload["cases"][0]["row"]], options, flipped, p0_as_of)[0]
    if flipped_p0["score"]["band_reason"] != "review_p0" or flipped_p0["score"]["band"] == "auto_brief":
        raise SystemExit("FAIL: v2 scorer must still keep Forced P0 in review")

    for row in first + list(neighbours.values()) + [solo_re, masked_row, held_row, lone_row] + p0_rows:
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
    parser.add_argument("--scorer", choices=["v1", "v2"], help="Override config active_scorer for this run.")
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
        if args.scorer:
            cfg.active_scorer = args.scorer
            cfg.validate()
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
