#!/usr/bin/env python3
"""Experimental multi-axis scorer (v2). v1 in score_pool.py stays the control.

P = 0.30*importance + 0.25*novelty + 0.20*relevance + 0.15*actionability + 0.10*freshness

Weights and per-type freshness τ live in config.json under score.v2. They are
a starting point, not a tuned optimum. Independent confidence is its own gate.
Forced P0 bypasses both the P gate and the confidence gate, and still cannot
auto-publish.

Rules always fill the dimensions. AI_RADAR_SCORE_LLM_URL only records
skipped_reason. This module does not open a socket. A future batch adapter can
overlay numbers; missing fields keep the rules values.

  python3 scripts/score_pool_v2.py --self-check
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from force_p0 import content_flags
    from ingest_x import IngestError
else:
    from .force_p0 import content_flags
    from .ingest_x import IngestError

DIMENSIONS = ("importance", "novelty", "relevance", "actionability", "freshness")

DEFAULT_V2: dict[str, Any] = {
    "weights": {
        "importance": 0.30,
        "novelty": 0.25,
        "relevance": 0.20,
        "actionability": 0.15,
        "freshness": 0.10,
    },
    "confidence_min": 0.45,
    "review_min": 0.40,
    "auto_min": 0.62,
    "freshness_tau_hours": {
        "vuln": 18.0,
        "product_launch": 30.0,
        "tutorial": 96.0,
        "analysis": 72.0,
        "default": 36.0,
    },
}


def _clamp(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 4)


def resolve_v2_config(raw: dict | None) -> dict:
    """Deep-merge config over the defaults. Unknown weight keys are rejected."""
    merged = {
        "weights": dict(DEFAULT_V2["weights"]),
        "confidence_min": DEFAULT_V2["confidence_min"],
        "review_min": DEFAULT_V2["review_min"],
        "auto_min": DEFAULT_V2["auto_min"],
        "freshness_tau_hours": dict(DEFAULT_V2["freshness_tau_hours"]),
    }
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise IngestError("score.v2 must be an object")
    weights = raw.get("weights")
    if weights is not None:
        if not isinstance(weights, dict):
            raise IngestError("score.v2.weights must be an object")
        unknown = set(weights) - set(DIMENSIONS)
        if unknown:
            raise IngestError(f"score.v2.weights has unknown keys: {sorted(unknown)}")
        for key, value in weights.items():
            merged["weights"][key] = float(value)
    for key in ("confidence_min", "review_min", "auto_min"):
        if key in raw:
            merged[key] = float(raw[key])
    taus = raw.get("freshness_tau_hours")
    if taus is not None:
        if not isinstance(taus, dict):
            raise IngestError("score.v2.freshness_tau_hours must be an object")
        for key, value in taus.items():
            if key not in DEFAULT_V2["freshness_tau_hours"]:
                raise IngestError(f"score.v2 freshness type {key!r} is unknown")
            merged["freshness_tau_hours"][key] = float(value)
    total = sum(float(merged["weights"][key]) for key in DIMENSIONS)
    if abs(total - 1.0) > 0.001:
        raise IngestError(f"score.v2 weights must sum to 1, got {total}")
    for key in DIMENSIONS:
        if float(merged["weights"][key]) < 0:
            raise IngestError("score.v2 weights must be ≥ 0")
    if not 0 <= merged["review_min"] <= merged["auto_min"] <= 1:
        raise IngestError("score.v2 thresholds must satisfy 0 ≤ review_min ≤ auto_min ≤ 1")
    if not 0 <= merged["confidence_min"] <= 1:
        raise IngestError("score.v2.confidence_min must be in [0, 1]")
    for key, value in merged["freshness_tau_hours"].items():
        if float(value) <= 0:
            raise IngestError(f"score.v2 freshness tau {key} must be > 0")
    return merged


def llm_batch_stub(rows: list[dict]) -> dict:
    """Batch shape for a later adapter. Identifiers only. Never POSTs the row."""
    url = (os.environ.get("AI_RADAR_SCORE_LLM_URL") or "").strip()
    return {
        "version": 1,
        "skipped_reason": "adapter_not_configured" if url else "rules_fallback",
        "items": [
            {"id": row.get("id"), "url": row.get("url_norm") or row.get("url")}
            for row in rows
        ],
    }


def overlay_dimensions(dimensions: dict[str, float], item: dict | None) -> tuple[dict[str, float], str]:
    """Optional local overlay. Any missing dimension keeps the rules value."""
    if not isinstance(item, dict):
        return dimensions, "rules"
    updated = dict(dimensions)
    touched = False
    for key in DIMENSIONS:
        if key in item and isinstance(item[key], (int, float)) and not isinstance(item[key], bool):
            updated[key] = _clamp(float(item[key]))
            touched = True
    return updated, "llm" if touched else "rules"


def freshness_of(age_hours: float | None, content_type: str, cfg: dict) -> float:
    if age_hours is None:
        return 0.55
    tau = float(cfg["freshness_tau_hours"].get(content_type) or cfg["freshness_tau_hours"]["default"])
    return _clamp(math.exp(-max(0.0, age_hours) / tau))


def blend(dimensions: dict[str, float], cfg: dict) -> float:
    total = 0.0
    for key in DIMENSIONS:
        total += float(cfg["weights"][key]) * float(dimensions[key])
    return _clamp(total)


def band_v2(
    score_p: float,
    confidence: float,
    *,
    primary: bool,
    practice: bool,
    status: str,
    official: bool,
    cfg: dict,
    forced: bool,
) -> tuple[str, str]:
    """Same publish locks as v1: practice, non-official, and P0 never auto-publish."""
    if forced:
        return "review", "review_p0"
    if status == "deferred":
        return "review", "review_deferred"
    gated = score_p < float(cfg["review_min"]) or confidence < float(cfg["confidence_min"])
    if gated:
        return "drop", "drop_low_score"
    if practice:
        return "review", "review_practice"
    if not primary:
        return "review", "review_no_primary"
    if not official:
        return "review", "review_not_official"
    if (
        score_p >= float(cfg["auto_min"])
        and confidence >= float(cfg["confidence_min"])
        and status == "active"
    ):
        return "auto_brief", "auto_primary"
    return "review", "review_score"


def score_v2(
    row: dict,
    *,
    age_hours: float | None,
    source_reliability: float,
    evidence_grade: float,
    independent_sources: int,
    evidence_n: int,
    spread_n: int,
    primary: bool,
    official: bool,
    practice: bool,
    actionability_raw: float,
    actionability_cap: float,
    status: str,
    cfg: dict,
    forced: bool,
    overlay: dict | None = None,
) -> dict:
    """Rules dimensions in [0, 1]. Confidence is not folded into P."""
    flags = content_flags(row)
    kinds = set((row.get("force_p0") or {}).get("kinds") or [])
    if forced and "runtime_vuln" in kinds:
        content_type = "vuln"
    elif forced and "frontier_launch" in kinds:
        content_type = "product_launch"
    else:
        content_type = flags["content_type"]

    importance = _clamp(source_reliability)
    if "runtime_vuln" in kinds or "frontier_launch" in kinds or content_type in {"vuln", "product_launch"}:
        importance = _clamp(max(importance, 0.86))
    elif "multi_a_tier" in kinds:
        importance = _clamp(max(importance, 0.74))

    novelty = 0.62
    if evidence_n <= 1 and spread_n > max(independent_sources, 1):
        novelty = 0.38
    role = (row.get("source") or {}).get("role_guess")
    if role == "report" and not primary:
        novelty = min(novelty, 0.5)
    if content_type in {"product_launch", "vuln"} and (primary or official or forced):
        novelty = max(novelty, 0.84)
    elif independent_sources <= 1 and spread_n <= 1:
        novelty = max(novelty, 0.74)
    novelty = _clamp(novelty)

    if content_type == "vuln":
        relevance = 0.72
    elif practice:
        relevance = 0.78
    elif content_type == "product_launch" or role == "primary":
        relevance = 0.8
    elif role == "analysis" or content_type == "tutorial":
        relevance = 0.7
    else:
        relevance = 0.42
    relevance = _clamp(relevance)

    if actionability_cap > 0:
        actionable = min(1.0, float(actionability_raw) / float(actionability_cap))
    else:
        actionable = 0.0
    if content_type == "vuln":
        actionable = max(actionable, 0.72)
    if content_type == "product_launch":
        actionable = max(actionable, 0.6)
    if flags["tool_choice"] or (row.get("force_p0") or {}).get("tool_choice"):
        actionable = max(actionable, 0.66)
    actionable = _clamp(actionable)

    fresh = freshness_of(age_hours, content_type, cfg)
    dimensions = {
        "importance": importance,
        "novelty": novelty,
        "relevance": relevance,
        "actionability": actionable,
        "freshness": fresh,
    }
    dimensions, method = overlay_dimensions(dimensions, overlay)
    score_p = blend(dimensions, cfg)

    confidence = 0.28 + 0.45 * float(evidence_grade)
    if official or primary:
        confidence += 0.12
    confidence += min(0.24, 0.12 * max(0, int(evidence_n) - 1))
    if role == "report" and int(evidence_n) == 0:
        confidence = min(confidence, 0.4)
    elif role == "report" and not official:
        confidence = min(confidence, 0.48)
    confidence = _clamp(confidence)

    band, reason = band_v2(
        score_p,
        confidence,
        primary=primary,
        practice=practice,
        status=status,
        official=official,
        cfg=cfg,
        forced=forced,
    )
    return {
        "p": score_p,
        "confidence": confidence,
        "band": band,
        "band_reason": reason,
        "content_type": content_type,
        "dimensions": dimensions,
        "weights": {key: float(cfg["weights"][key]) for key in DIMENSIONS},
        "method": method,
        "llm": {"skipped_reason": "rules_fallback"},
    }


def self_check() -> None:
    cfg = resolve_v2_config(None)
    dims = {key: 1.0 for key in DIMENSIONS}
    if blend(dims, cfg) != 1.0:
        raise SystemExit("FAIL: v2 weights should blend ones to 1")
    try:
        resolve_v2_config({"weights": {"importance": 0.5}})
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: partial weights that no longer sum to 1 must be rejected")

    row = {
        "id": "cand-20261022-aaaaaaaaaaa1",
        "title": "FIXTURE Claude Duet research preview",
        "snippet": "FIXTURE Pro waitlist is open.",
        "url": "https://example.com/fixture-duet",
        "source": {"channel": "x", "handle": "someone", "role_guess": "report"},
        "force_p0": {"active": True, "kinds": ["frontier_launch"], "tool_choice": True},
    }
    scored = score_v2(
        row,
        age_hours=80,
        source_reliability=0.4,
        evidence_grade=0.42,
        independent_sources=1,
        evidence_n=0,
        spread_n=1,
        primary=False,
        official=False,
        practice=False,
        actionability_raw=0.0,
        actionability_cap=0.12,
        status="active",
        cfg=cfg,
        forced=True,
    )
    if scored["band"] != "review" or scored["band_reason"] != "review_p0":
        raise SystemExit(f"FAIL: P0 must bypass v2 gates, got {scored['band']}/{scored['band_reason']}")
    if scored["content_type"] != "product_launch":
        raise SystemExit(f"FAIL: launch freshness type, got {scored['content_type']}")
    vuln_fresh = freshness_of(18, "vuln", cfg)
    analysis_fresh = freshness_of(18, "analysis", cfg)
    if not vuln_fresh < analysis_fresh:
        raise SystemExit(f"FAIL: vuln τ should decay faster than analysis ({vuln_fresh} vs {analysis_fresh})")
    manual = 0
    for key in DIMENSIONS:
        manual += cfg["weights"][key] * scored["dimensions"][key]
    if abs(manual - scored["p"]) > 0.001:
        raise SystemExit(f"FAIL: P {scored['p']} != weighted sum {manual}")
    stub = llm_batch_stub([row])
    if stub["skipped_reason"] != "rules_fallback" or "snippet" in str(stub):
        raise SystemExit(f"FAIL: llm stub must stay local and identifier-only: {stub}")
    over, method = overlay_dimensions(scored["dimensions"], {"importance": 0.2})
    if method != "llm" or over["importance"] != 0.2:
        raise SystemExit("FAIL: local overlay should replace only provided dimensions")
    print("OK score_pool_v2 self-check")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Score v2 self-check. No network.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    parser.error("pass --self-check; production scoring goes through scripts/score_pool.py")
    return 2


if __name__ == "__main__":
    sys.exit(main())
