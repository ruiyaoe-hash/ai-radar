#!/usr/bin/env python3
"""Compare v1 and v2 scores on the same candidate rows.

Reads a private-pool JSONL extract or the synthetic file in testdata/backtest/.
Writes a comparison table and, once Rui's labels exist, the metric stubs.
Does not publish, does not call a model, and does not need the private pool
for --self-check.

  python3 scripts/backtest_score_ab.py --self-check
  python3 scripts/backtest_score_ab.py \\
      --input testdata/backtest/sample.jsonl \\
      --labels testdata/backtest/labels.sample.csv \\
      --as-of 2026-10-22T12:00:00Z \\
      --out-dir /tmp/ai-radar-ab
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import options_from_repo
    from ingest_x import IngestError, assert_not_public, parse_utc
    from score_pool import load_score_config, score_records
else:
    from .annotate_gates import options_from_repo
    from .ingest_x import IngestError, assert_not_public, parse_utc
    from .score_pool import load_score_config, score_records

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "testdata" / "backtest" / "sample.jsonl"
LABEL_TEMPLATE = ROOT / "testdata" / "backtest" / "labels.template.csv"
LABEL_SAMPLE = ROOT / "testdata" / "backtest" / "labels.sample.csv"

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


def compare_rows(rows: list[dict], as_of: str | None = None) -> list[dict]:
    """Run v1 (band) and shadow v2 on the same rows. Input rows are not mutated."""
    cfg = load_score_config(ROOT)
    cfg.active_scorer = "v1"
    cfg.shadow_v2 = True
    cfg.validate()
    clock = parse_utc(as_of) if as_of else parse_utc("2026-10-22T12:00:00Z")
    options = options_from_repo(clock)
    scored = {str(row.get("id")): row for row in score_records(rows, options, cfg, clock)}
    table = []
    for original in rows:
        row = scored.get(str(original.get("id")), original)
        score = row.get("score") or {}
        v2 = score.get("v2") or {}
        dims = v2.get("dimensions") or {}
        spec = row.get("force_p0") or {}
        v1_band = score.get("band") or ""
        v2_band = v2.get("band") or ""
        handle = (row.get("source") or {}).get("handle") or ""
        table.append(
            {
                "cid": row.get("id") or "",
                "url": row.get("url_norm") or row.get("url") or "",
                "handle": handle,
                "v1_value": _num(score.get("value")) if score else "",
                "v1_band": v1_band,
                "v1_reason": score.get("band_reason") or "",
                "v2_importance": _num(dims.get("importance")),
                "v2_novelty": _num(dims.get("novelty")),
                "v2_relevance": _num(dims.get("relevance")),
                "v2_actionability": _num(dims.get("actionability")),
                "v2_freshness": _num(dims.get("freshness")),
                "v2_p": _num(v2.get("p")),
                "v2_confidence": _num(v2.get("confidence")),
                "v2_band": v2_band,
                "v2_reason": v2.get("band_reason") or "",
                "content_type": v2.get("content_type") or "",
                "force_p0": "yes" if spec.get("active") else "no",
                "p0_kinds": ",".join(spec.get("kinds") or []),
                "p0_default": spec.get("default_action") or "",
                "disagreement": "yes" if v1_band and v2_band and v1_band != v2_band else "no",
                "_published_at": row.get("published_at"),
                "_ingested_at": row.get("ingested_at"),
            }
        )
    return table


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
    print("OK backtest_score_ab self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B compare v1 and v2 scores. No network.")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--input", help="Candidate JSONL. Defaults to testdata/backtest/sample.jsonl.")
    parser.add_argument("--labels", help="Rui's label CSV. Metrics are skipped when omitted.")
    parser.add_argument("--as-of", default="2026-10-22T12:00:00Z")
    parser.add_argument("--out-dir", help="Directory for comparison.csv, comparison.md, metrics.md.")
    parser.add_argument("--emit-template", help="Write a blank label CSV for these rows and exit.")
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    try:
        source = Path(args.input) if args.input else SAMPLE
        rows = load_jsonl(source)
        if args.emit_template:
            emit_template(rows, Path(args.emit_template))
            print(f"OK backtest_score_ab: template {args.emit_template}")
            return 0
        table = compare_rows(rows, args.as_of)
        metrics = None
        if args.labels:
            metrics = compute_metrics(table, load_labels(Path(args.labels)), topk=args.topk)
        if args.out_dir:
            out = Path(args.out_dir)
            write_csv(out / "comparison.csv", table)
            write_markdown(out / "comparison.md", table)
            if metrics is not None:
                metrics_path = out / "metrics.md"
                assert_not_public(metrics_path)
                metrics_path.write_text(metrics_markdown(metrics), encoding="utf-8")
                (out / "metrics.json").write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            print(f"OK backtest_score_ab: {out}")
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
