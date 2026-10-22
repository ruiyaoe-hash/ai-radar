#!/usr/bin/env python3
"""Compare v1 and v2 scores on the same candidate rows.

Reads a private-pool JSONL extract or the synthetic files in testdata/backtest/.
The primary labeling path is a chat pack: Alba pastes numbered A/B choices,
Rui answers A or B (or 相同 when both sides match). A wide CSV remains for
batch export. Spreadsheet labels are optional, not the path Rui fills by hand.

Does not publish, does not call a model, and does not need the private pool
for --self-check.

  python3 scripts/backtest_score_ab.py --self-check
  python3 scripts/backtest_score_ab.py --pack --out-dir /tmp/ai-radar-ab
  python3 scripts/backtest_score_ab.py --pack --picks /tmp/picks.txt --out-dir /tmp/ai-radar-ab
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import options_from_repo
    from card_copy import build_card_copy
    from ingest_x import IngestError, assert_not_public, parse_utc
    from score_pool import cluster_key, counts_independent, load_score_config, score_records, source_identity
else:
    from .annotate_gates import options_from_repo
    from .card_copy import build_card_copy
    from .ingest_x import IngestError, assert_not_public, parse_utc
    from .score_pool import cluster_key, counts_independent, load_score_config, score_records, source_identity

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "testdata" / "backtest" / "sample.jsonl"
CHAT_PACK_ROWS = ROOT / "testdata" / "backtest" / "chat_pack.jsonl"
CHAT_PACK_MD = ROOT / "testdata" / "backtest" / "labeling-chat-pack.md"
LABEL_TEMPLATE = ROOT / "testdata" / "backtest" / "labels.template.csv"
LABEL_SAMPLE = ROOT / "testdata" / "backtest" / "labels.sample.csv"
PACK_MIN = 20
PACK_MAX = 40
_SCORE_LEAK = re.compile(r"\d+\.\d+|value\s*=|PHP2Shell|research preview", re.I)
_CHOICE_RE = re.compile(r"^\s*(\d+)\s*[.)、:：,]?\s*(A|B|相同|same|tie)\s*$", re.I)

COLUMNS = [
    "cid",
    "url",
    "handle",
    "v1_value",
    "v1_band",
    "v1_reason",
    "v2_importance",
    "v2_novelty",
    "v2_relevance",
    "v2_actionability",
    "v2_freshness",
    "v2_p",
    "v2_confidence",
    "v2_band",
    "v2_reason",
    "content_type",
    "force_p0",
    "p0_kinds",
    "p0_default",
    "evidence_label",
    "suggested_action",
    "high_priority_review",
    "watch_reason",
    "happened",
    "v1_choice",
    "v2_choice",
    "choice_split",
    "disagreement",
]
LABEL_FIELDS = [
    "cid",
    "url",
    "important",
    "duplicate",
    "low_value",
    "actionable",
    "evidence_sufficient",
    "should_p0",
    "event_at",
    "notes",
]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestError(f"{path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise IngestError(f"{path}:{line_no}: expected an object")
        rows.append(row)
    if not rows:
        raise IngestError(f"{path}: empty sample")
    return rows


def _num(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.4f}"
    return ""


def _hours(start: str | None, end: str | None) -> float | None:
    if not isinstance(start, str) or not isinstance(end, str) or not start or not end:
        return None
    try:
        return (parse_utc(end) - parse_utc(start)).total_seconds() / 3600.0
    except IngestError:
        return None


def _without_pack_line(rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """ab_line is the chat one-liner. It must not enter the scorer."""
    clean = []
    lines: dict[str, str] = {}
    for row in rows:
        item = dict(row)
        line = item.pop("ab_line", "")
        lines[str(item.get("id") or "")] = line.strip() if isinstance(line, str) else ""
        clean.append(item)
    return clean, lines


def _band_zh(band: str) -> str:
    return {"auto_brief": "自动快讯", "review": "人工看", "drop": "不公开"}.get(band, "未打分")


def _priority_zh(reason: str, high: bool) -> str:
    if high or reason == "review_p0":
        return "优先审"
    if reason == "review_deferred":
        return "本期不上"
    if reason == "review_practice":
        return "实操待核"
    return "普通"


def _choice_line(band: str, reason: str, copy: dict, scored: bool) -> str:
    """Compact side: 档 · 优先 · 动作 · 证据. No raw scores."""
    if not scored:
        return "未打分 · — · — · —"
    high = bool(copy.get("high_priority_review")) or reason == "review_p0"
    action = copy.get("suggested_action") or "—"
    evidence = copy.get("evidence_label") or "—"
    return f"{_band_zh(band)} · {_priority_zh(reason, high)} · {action} · {evidence}"


def _independent_counts(scored: list[dict]) -> dict[str, int]:
    buckets: dict[str, set[str]] = defaultdict(set)
    for row in scored:
        if counts_independent(row):
            buckets[cluster_key(row)].add(source_identity(row))
    return {key: len(ids) for key, ids in buckets.items()}


def compare_rows(rows: list[dict], as_of: str | None = None) -> list[dict]:
    """Run v1 (band) and shadow v2 on the same rows. Input rows are not mutated."""
    cfg = load_score_config(ROOT)
    cfg.active_scorer = "v1"
    cfg.shadow_v2 = True
    cfg.validate()
    clock = parse_utc(as_of) if as_of else parse_utc("2026-10-22T12:00:00Z")
    options = options_from_repo(clock)
    clean, happened = _without_pack_line(rows)
    scored_rows = score_records(clean, options, cfg, clock)
    scored = {str(row.get("id")): row for row in scored_rows}
    counts = _independent_counts(scored_rows)
    table = []
    for original in clean:
        row = scored.get(str(original.get("id")), original)
        score = row.get("score") or {}
        v2 = score.get("v2") or {}
        dims = v2.get("dimensions") or {}
        spec = row.get("force_p0") or {}
        copy = row.get("card_copy") if isinstance(row.get("card_copy"), dict) else {}
        v1_band = score.get("band") or ""
        v2_band = v2.get("band") or ""
        v1_reason = score.get("band_reason") or ""
        v2_reason = v2.get("band_reason") or ""
        handle = (row.get("source") or {}).get("handle") or ""
        scored_flag = bool(score)
        if scored_flag and v2_band:
            v2_copy = build_card_copy(
                row,
                official=bool(score.get("official_source")),
                independent_n=counts.get(cluster_key(row), 1),
                band=v2_band,
                band_reason=v2_reason,
                edition=str(score.get("edition_eligibility") or ""),
            )
        else:
            v2_copy = {}
        v1_choice = _choice_line(v1_band, v1_reason, copy, scored_flag)
        v2_choice = _choice_line(v2_band, v2_reason, v2_copy, scored_flag and bool(v2_band))
        table.append(
            {
                "cid": row.get("id") or "",
                "url": row.get("url_norm") or row.get("url") or "",
                "handle": handle,
                "v1_value": _num(score.get("value")) if score else "",
                "v1_band": v1_band,
                "v1_reason": v1_reason,
                "v2_importance": _num(dims.get("importance")),
                "v2_novelty": _num(dims.get("novelty")),
                "v2_relevance": _num(dims.get("relevance")),
                "v2_actionability": _num(dims.get("actionability")),
                "v2_freshness": _num(dims.get("freshness")),
                "v2_p": _num(v2.get("p")),
                "v2_confidence": _num(v2.get("confidence")),
                "v2_band": v2_band,
                "v2_reason": v2_reason,
                "content_type": v2.get("content_type") or "",
                "force_p0": "yes" if spec.get("active") else "no",
                "p0_kinds": ",".join(spec.get("kinds") or []),
                "p0_default": spec.get("default_action") or "",
                "evidence_label": copy.get("evidence_label") or "",
                "suggested_action": copy.get("suggested_action") or "",
                "high_priority_review": "yes" if copy.get("high_priority_review") else "no",
                "watch_reason": copy.get("watch_reason") or "",
                "happened": happened.get(str(row.get("id") or ""), ""),
                "v1_choice": v1_choice,
                "v2_choice": v2_choice,
                "choice_split": "yes" if v1_choice != v2_choice else "no",
                "disagreement": "yes" if v1_band and v2_band and v1_band != v2_band else "no",
                "_published_at": row.get("published_at"),
                "_ingested_at": row.get("ingested_at"),
            }
        )
    return table


def render_chat_pack(table: list[dict]) -> str:
    """Numbered list Alba can paste. One event line, then A and B, no scores."""
    lines = [
        "# 对照选择题",
        "",
        "Alba 把下面的条目分批贴到聊天里。Rui 每条只回 A 或 B：A 是现在的 v1 决定，B 是实验的 v2 决定。",
        "两边相同时回「相同」。不用填多列表。分数不出现在这里。",
        "每条的四个字是：档 · 优先 · 动作 · 证据。",
        "",
    ]
    for index, row in enumerate(table, start=1):
        happened = row.get("happened") or "这条没有单独的一句说明。"
        lines.append(f"{index}. {happened}")
        lines.append(f"   A · v1：{row.get('v1_choice')}")
        lines.append(f"   B · v2：{row.get('v2_choice')}")
        if row.get("choice_split") == "yes":
            lines.append("   两边不同。回 A 或 B。")
        else:
            lines.append("   两边相同。认可这个决定就回「相同」。")
        lines.append("")
    lines.extend(
        [
            "## 回执",
            "",
            "一行一条，例如 `1 A`、`2 B`、`3 相同`。存成文本后：",
            "",
            "```bash",
            "python3 scripts/backtest_score_ab.py --pack --picks /tmp/picks.txt --out-dir /tmp/ai-radar-ab",
            "```",
            "",
            "汇总看 `picks-metrics.md`。只有两边不同、而且选了 A 或 B 的条目才计入偏好。两边相同的「相同」表示接受这个共同决定，不记成某一边赢。",
            "",
        ]
    )
    return "\n".join(lines)


def write_chat_pack(path: Path, table: list[dict]) -> None:
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_chat_pack(table), encoding="utf-8")


def load_picks(path: Path) -> dict[int, str]:
    """Accept `1 A` lines or a CSV with columns n,choice. Blank lines and # comments are ignored."""
    text = path.read_text(encoding="utf-8")
    picks: dict[int, str] = {}
    body = "\n".join(line for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
    stripped = body.lstrip()
    if stripped.lower().startswith("n,") or stripped.lower().startswith("n\t"):
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {name.strip().lower() for name in (reader.fieldnames or [])}
            if "n" not in fields or "choice" not in fields:
                raise IngestError(f"{path}: picks CSV needs columns n,choice")
            for row in reader:
                number = (row.get("n") or row.get("N") or "").strip()
                choice = (row.get("choice") or row.get("Choice") or "").strip()
                if not number and not choice:
                    continue
                _store_pick(picks, number, choice, path)
        return picks
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matched = _CHOICE_RE.match(line)
        if not matched:
            raise IngestError(f"{path}:{line_no}: expected '1 A', '2 B', or '3 相同'")
        _store_pick(picks, matched.group(1), matched.group(2), path)
    return picks


def _store_pick(picks: dict[int, str], number: str, choice: str, path: Path) -> None:
    try:
        index = int(number)
    except ValueError as exc:
        raise IngestError(f"{path}: bad item number {number}") from exc
    if index < 1:
        raise IngestError(f"{path}: item numbers start at 1")
    token = choice.strip().lower()
    if token == "a":
        normalized = "A"
    elif token == "b":
        normalized = "B"
    elif token in {"相同", "same", "tie"}:
        normalized = "相同"
    else:
        raise IngestError(f"{path}: choice must be A, B, or 相同")
    if index in picks:
        raise IngestError(f"{path}: item {index} was answered twice")
    picks[index] = normalized


def compute_pick_metrics(table: list[dict], picks: dict[int, str]) -> dict:
    """Scorer preference from A/B replies. Ties do not count as a win."""

    def rate(hits: int, total: int) -> float | None:
        if total <= 0:
            return None
        return round(hits / total, 4)

    a_on_split = b_on_split = split_shown = split_unpicked = 0
    same_shown = same_accepted = same_other = 0
    p0_in_pack = p0_accepted = 0
    unknown = [index for index in picks if index < 1 or index > len(table)]
    if unknown:
        raise IngestError(f"picks refer to items outside 1..{len(table)}: {unknown}")
    for index, row in enumerate(table, start=1):
        split = row.get("choice_split") == "yes"
        choice = picks.get(index)
        p0 = row.get("force_p0") == "yes"
        if p0:
            p0_in_pack += 1
        if split:
            split_shown += 1
            if choice == "A":
                a_on_split += 1
            elif choice == "B":
                b_on_split += 1
            else:
                split_unpicked += 1
        else:
            same_shown += 1
            if choice == "相同":
                same_accepted += 1
                if p0:
                    p0_accepted += 1
            elif choice in {"A", "B"}:
                same_other += 1
    decided = a_on_split + b_on_split
    return {
        "pack_size": len(table),
        "picked": len(picks),
        "split_shown": split_shown,
        "split_unpicked": split_unpicked,
        "a_on_split": a_on_split,
        "b_on_split": b_on_split,
        "a_prefer_rate": rate(a_on_split, decided),
        "b_prefer_rate": rate(b_on_split, decided),
        "same_shown": same_shown,
        "same_accepted": same_accepted,
        "same_answered_anyway": same_other,
        "p0_in_pack": p0_in_pack,
        "p0_same_accepted": p0_accepted,
    }


def picks_markdown(metrics: dict) -> str:
    lines = [
        "# 聊天对照汇总",
        "",
        "只统计两边不同、而且回了 A 或 B 的条目。没有这种条目时，偏好是空的，不写成 0。",
        "两边相同的「相同」表示接受共同决定，不记成 v1 或 v2 赢。",
        "",
    ]
    for key, value in metrics.items():
        shown = "" if value is None else value
        lines.append(f"- {key}: {shown}")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, table: list[dict]) -> None:
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(table)


def write_markdown(path: Path, table: list[dict]) -> None:
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(COLUMNS) + " |"
    rule = "| " + " | ".join("---" for _ in COLUMNS) + " |"
    lines = ["# v1 / v2 对照", "", header, rule]
    for row in table:
        lines.append("| " + " | ".join(str(row.get(column) or "") for column in COLUMNS) + " |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def emit_template(rows: list[dict], path: Path) -> None:
    assert_not_public(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "cid": row.get("id") or "",
                    "url": row.get("url_norm") or row.get("url") or "",
                    "important": "",
                    "duplicate": "",
                    "low_value": "",
                    "actionable": "",
                    "evidence_sufficient": "",
                    "should_p0": "",
                    "event_at": "",
                    "notes": "",
                }
            )


def _flag(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text == "":
        return None
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return None


def load_labels(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in LABEL_FIELDS if reader.fieldnames and name not in reader.fieldnames]
        if missing:
            raise IngestError(f"{path}: label columns missing {missing}")
        labels = {}
        for row in reader:
            cid = (row.get("cid") or "").strip()
            if not cid:
                continue
            labels[cid] = row
        return labels


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def compute_metrics(table: list[dict], labels: dict[str, dict], topk: int = 5) -> dict:
    """Stubs. Empty labels leave the rates null instead of pretending a score."""

    def labeled_rows():
        for row in table:
            label = labels.get(row["cid"])
            if label:
                yield row, label

    def rate(hits: int, total: int) -> float | None:
        if total <= 0:
            return None
        return round(hits / total, 4)

    p0_hit = p0_total = p0_flagged = p0_flagged_right = 0
    auto_v1_hit = auto_v1_total = auto_v2_hit = auto_v2_total = 0
    suppress_v1 = suppress_v2 = promote_v1 = promote_v2 = 0
    review_v1 = review_v2 = 0
    delays: list[float] = []
    event_delays: list[float] = []
    useful_pool_v1: list[tuple[float, int]] = []
    useful_pool_v2: list[tuple[float, int]] = []

    for row in table:
        if row["v1_band"] == "review":
            review_v1 += 1
        if row["v2_band"] == "review":
            review_v2 += 1
        delay = _hours(row.get("_published_at"), row.get("_ingested_at"))
        if delay is not None:
            delays.append(delay)

    for row, label in labeled_rows():
        important = _flag(label.get("important"))
        duplicate = _flag(label.get("duplicate"))
        low_value = _flag(label.get("low_value"))
        should_p0 = _flag(label.get("should_p0"))
        forced = row["force_p0"] == "yes"
        if should_p0 == 1:
            p0_total += 1
            if forced:
                p0_hit += 1
        if forced:
            p0_flagged += 1
            if should_p0 == 1:
                p0_flagged_right += 1
        wanted = important == 1 and duplicate != 1 and low_value != 1
        if wanted and row["v1_band"] == "drop":
            suppress_v1 += 1
        if wanted and row["v2_band"] == "drop":
            suppress_v2 += 1
        noisy = low_value == 1 or duplicate == 1
        if noisy and row["v1_band"] == "auto_brief":
            promote_v1 += 1
        if noisy and row["v2_band"] == "auto_brief":
            promote_v2 += 1
        if row["v1_band"] == "auto_brief" and important is not None:
            auto_v1_total += 1
            if important == 1 and duplicate != 1 and low_value != 1:
                auto_v1_hit += 1
        if row["v2_band"] == "auto_brief" and important is not None:
            auto_v2_total += 1
            if important == 1 and duplicate != 1 and low_value != 1:
                auto_v2_hit += 1
        if important is not None and row["v1_value"] != "":
            useful_pool_v1.append((float(row["v1_value"]), important))
        if important is not None and row["v2_p"] != "":
            useful_pool_v2.append((float(row["v2_p"]), important))
        event_delay = _hours(label.get("event_at"), row.get("_ingested_at"))
        if event_delay is not None:
            event_delays.append(event_delay)

    def topk_rate(pool: list[tuple[float, int]]) -> float | None:
        if not pool:
            return None
        ordered = sorted(pool, key=lambda item: (-item[0],))
        chosen = ordered[: max(1, topk)]
        return round(sum(flag for _score, flag in chosen) / len(chosen), 4)

    return {
        "rows": len(table),
        "labeled": len(list(labeled_rows())),
        "p0_recall": rate(p0_hit, p0_total),
        "p0_precision": rate(p0_flagged_right, p0_flagged),
        "auto_brief_precision_v1": rate(auto_v1_hit, auto_v1_total),
        "auto_brief_precision_v2": rate(auto_v2_hit, auto_v2_total),
        "topk_useful_v1": topk_rate(useful_pool_v1),
        "topk_useful_v2": topk_rate(useful_pool_v2),
        "false_suppress_v1": suppress_v1,
        "false_suppress_v2": suppress_v2,
        "false_promote_v1": promote_v1,
        "false_promote_v2": promote_v2,
        "discovery_delay_hours_mean": _mean(delays),
        "event_delay_hours_mean": _mean(event_delays),
        "review_cost_proxy_v1": review_v1,
        "review_cost_proxy_v2": review_v2,
        "topk": topk,
    }


def metrics_markdown(metrics: dict) -> str:
    lines = ["# 对照指标", "", "有标注才算率。没有分母时写空，不拿 0 冒充。", ""]
    for key, value in metrics.items():
        shown = "" if value is None else value
        lines.append(f"- {key}: {shown}")
    lines.append("")
    return "\n".join(lines)


def self_check() -> None:
    if not SAMPLE.is_file() or not LABEL_TEMPLATE.is_file() or not LABEL_SAMPLE.is_file():
        raise SystemExit("FAIL: backtest fixtures missing")
    header = LABEL_TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    for name in ("important", "duplicate", "low_value", "actionable", "evidence_sufficient", "should_p0", "notes"):
        if name not in header.split(","):
            raise SystemExit(f"FAIL: label template missing {name}")
    rows = load_jsonl(SAMPLE)
    first = compare_rows(rows, "2026-10-22T12:00:00Z")
    second = compare_rows(rows, "2026-10-22T12:00:00Z")
    if first != second:
        raise SystemExit("FAIL: backtest compare is not deterministic")
    by_cid = {row["cid"]: row for row in first}
    duet = by_cid["cand-20261022-b0b000000001"]
    vuln = by_cid["cand-20261022-b0b000000002"]
    ordinary = by_cid["cand-20261022-b0b000000003"]
    solo = by_cid["cand-20261022-b0b000000004"]
    reprint = by_cid["cand-20261022-b0b000000005"]
    held = by_cid["cand-20261022-b0b000000006"]
    if duet["force_p0"] != "yes" or "frontier_launch" not in duet["p0_kinds"] or duet["v1_reason"] != "review_p0":
        raise SystemExit(f"FAIL: duet-class row was not forced P0: {duet}")
    if duet["v1_band"] == "auto_brief":
        raise SystemExit("FAIL: duet-class row must not auto-publish")
    if (
        duet["high_priority_review"] != "yes"
        or duet["suggested_action"] != "持续观察"
        or any(ch.isdigit() for ch in duet["watch_reason"])
    ):
        raise SystemExit(f"FAIL: duet card copy {duet['suggested_action']} {duet['watch_reason']}")
    if vuln["suggested_action"] != "立即试用" or vuln["high_priority_review"] != "yes":
        raise SystemExit(f"FAIL: vuln card copy {vuln['suggested_action']}")
    if (
        ordinary["evidence_label"] != "官方原始信息"
        or ordinary["suggested_action"] != "持续观察"
        or ordinary["high_priority_review"] != "no"
    ):
        raise SystemExit(f"FAIL: ordinary card copy {ordinary['evidence_label']} {ordinary['suggested_action']}")
    if held["suggested_action"] != "暂缓" or held["high_priority_review"] != "no":
        raise SystemExit(f"FAIL: held card copy {held['suggested_action']}")
    if vuln["force_p0"] != "yes" or "runtime_vuln" not in vuln["p0_kinds"] or vuln["v1_band"] != "review":
        raise SystemExit(f"FAIL: vuln-class row was not forced P0: {vuln}")
    if ordinary["v1_band"] != "auto_brief" or ordinary["force_p0"] == "yes":
        raise SystemExit(f"FAIL: ordinary official row changed publish behavior: {ordinary}")
    if solo["v1_value"] and reprint["v1_band"]:
        raise SystemExit("FAIL: a no_new_info reprint must not be rescored into a band")
    if float(solo["v2_p"]) <= 0:
        raise SystemExit("FAIL: v2 P missing on the solo row")
    if held["v1_reason"] != "review_deferred" or held["v1_band"] == "drop":
        raise SystemExit(f"FAIL: edition hold collapsed into a drop: {held}")
    labels = load_labels(LABEL_SAMPLE)
    metrics = compute_metrics(first, labels, topk=5)
    if metrics["p0_recall"] != 1:
        raise SystemExit(f"FAIL: fixture P0 recall {metrics['p0_recall']}")
    if not metrics["false_promote_v1"]:
        raise SystemExit(f"FAIL: expected a false auto_brief on the ordinary low-value label: {metrics}")
    if metrics["discovery_delay_hours_mean"] is None or metrics["review_cost_proxy_v1"] < 1:
        raise SystemExit(f"FAIL: delay or review proxy missing: {metrics}")
    blob = json.dumps(first)
    if "research preview" in blob or "PHP2Shell" in blob:
        raise SystemExit("FAIL: comparison table copied source text")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ab"
        write_csv(out / "comparison.csv", first)
        write_markdown(out / "comparison.md", first)
        (out / "metrics.md").write_text(metrics_markdown(metrics), encoding="utf-8")
        text = (out / "comparison.csv").read_text(encoding="utf-8")
        if "snippet" in text.splitlines()[0]:
            raise SystemExit("FAIL: csv header has a body column")
    public_out = ROOT / "public" / "_ab_should_not_write.csv"
    try:
        write_csv(public_out, first[:1])
    except IngestError:
        pass
    else:
        raise SystemExit("FAIL: backtest wrote under public/")
    if public_out.exists():
        public_out.unlink()
        raise SystemExit("FAIL: public csv was created")
    _check_chat_pack()
    print("OK backtest_score_ab self-check")


def _check_chat_pack() -> None:
    if not CHAT_PACK_ROWS.is_file() or not CHAT_PACK_MD.is_file():
        raise SystemExit("FAIL: chat pack fixtures missing")
    rows = load_jsonl(CHAT_PACK_ROWS)
    if not PACK_MIN <= len(rows) <= PACK_MAX:
        raise SystemExit(f"FAIL: chat pack must have {PACK_MIN}–{PACK_MAX} rows, got {len(rows)}")
    table = compare_rows(rows, "2026-10-22T12:00:00Z")
    kinds = " ".join(row["p0_kinds"] for row in table)
    if "frontier_launch" not in kinds or "runtime_vuln" not in kinds:
        raise SystemExit(f"FAIL: chat pack lost a P0 kind: {kinds}")
    rendered = render_chat_pack(table)
    if rendered != CHAT_PACK_MD.read_text(encoding="utf-8"):
        raise SystemExit("FAIL: testdata/backtest/labeling-chat-pack.md drifted from the harness")
    if _SCORE_LEAK.search(rendered):
        raise SystemExit("FAIL: chat pack copied a score or a source phrase")
    numbered = [line for line in rendered.splitlines() if re.match(r"^\d+\. ", line)]
    if len(numbered) != len(table):
        raise SystemExit("FAIL: chat pack numbering does not match the rows")
    if not any(row["force_p0"] == "yes" and "frontier_launch" in row["p0_kinds"] for row in table):
        raise SystemExit("FAIL: chat pack has no duet-class P0")
    if not any(row["force_p0"] == "yes" and "runtime_vuln" in row["p0_kinds"] for row in table):
        raise SystemExit("FAIL: chat pack has no vuln-class P0")
    empty = compute_pick_metrics(table, {})
    if empty["a_prefer_rate"] is not None or empty["b_prefer_rate"] is not None:
        raise SystemExit(f"FAIL: no deciding picks must leave the preference empty: {empty}")
    if empty["p0_in_pack"] < 2:
        raise SystemExit(f"FAIL: chat pack needs both P0 shapes: {empty}")
    sample = "1 A\n# note\n2 B\n"
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "picks.txt"
        path.write_text(sample, encoding="utf-8")
        loaded = load_picks(path)
        if loaded != {1: "A", 2: "B"}:
            raise SystemExit(f"FAIL: pick parser {loaded}")
        write_chat_pack(path.with_name("labeling-chat-pack.md"), table[:1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B compare v1 and v2 scores. No network.")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--input", help="Candidate JSONL. Defaults to the small sample, or the chat pack with --pack.")
    parser.add_argument("--pack", action="store_true", help="Use the chat-pack fixtures and write labeling-chat-pack.md.")
    parser.add_argument("--labels", help="Optional spreadsheet labels. Not the primary labeling path.")
    parser.add_argument("--picks", help="Chat replies: '1 A' / '2 B' / '3 相同', or CSV n,choice.")
    parser.add_argument("--as-of", default="2026-10-22T12:00:00Z")
    parser.add_argument("--out-dir", help="Directory for comparison.csv, labeling-chat-pack.md, and metrics.")
    parser.add_argument("--emit-template", help="Write a blank label CSV for these rows and exit.")
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    try:
        if args.pack and args.input:
            raise IngestError("--pack already selects the chat-pack fixtures; drop --input")
        source = Path(args.input) if args.input else (CHAT_PACK_ROWS if args.pack else SAMPLE)
        rows = load_jsonl(source)
        if args.emit_template:
            emit_template(rows, Path(args.emit_template))
            print(f"OK backtest_score_ab: template {args.emit_template}")
            return 0
        table = compare_rows(rows, args.as_of)
        metrics = None
        if args.labels:
            metrics = compute_metrics(table, load_labels(Path(args.labels)), topk=args.topk)
        pick_metrics = None
        if args.picks:
            pick_metrics = compute_pick_metrics(table, load_picks(Path(args.picks)))
        if args.out_dir:
            out = Path(args.out_dir)
            write_csv(out / "comparison.csv", table)
            write_markdown(out / "comparison.md", table)
            write_chat_pack(out / "labeling-chat-pack.md", table)
            if metrics is not None:
                metrics_path = out / "metrics.md"
                assert_not_public(metrics_path)
                metrics_path.write_text(metrics_markdown(metrics), encoding="utf-8")
                (out / "metrics.json").write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if pick_metrics is not None:
                picks_path = out / "picks-metrics.md"
                assert_not_public(picks_path)
                picks_path.write_text(picks_markdown(pick_metrics), encoding="utf-8")
                (out / "picks-metrics.json").write_text(
                    json.dumps(pick_metrics, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            print(f"OK backtest_score_ab: {out}")
        elif args.pack or args.picks:
            sys.stdout.write(render_chat_pack(table))
            if pick_metrics is not None:
                print(picks_markdown(pick_metrics), file=sys.stderr)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(table)
            if metrics is not None:
                print(metrics_markdown(metrics), file=sys.stderr)
        return 0
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
