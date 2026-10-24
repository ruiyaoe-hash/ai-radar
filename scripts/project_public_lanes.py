#!/usr/bin/env python3
"""Place finished public cards for 实战手册 and 专题观察.

抓取 already puts practice handles into the private pool. 判定 parks them on
review_practice and never writes a public card. This is the 上站 step: a row
with at least two finished Chinese steps becomes a practice card; a long-horizon
analysis that is not a news brief and not a pick becomes a watch item.

Rows that are still English, unfinished, low-score, or forced onto the pick
queue are left in the pool. Nothing here writes briefs.

  python3 scripts/project_public_lanes.py --self-check
  python3 scripts/project_public_lanes.py --pool-dir ../ai-radar-pool
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import read_pool
    from card_copy import refuses_auto_publish
    from editorial_zh import edit_pair, reader_lines, visitor_ready
    from force_p0 import content_flags
    from generate_derived import safe_http_url
    from ingest_x import SHANGHAI, IngestError, parse_utc
    from prompt_guard import find_instruction_override, strip_raw_post_fields
    from score_pool import is_official_row, is_practice_row, load_score_config
    from shift_ingest_x_to_pool import assert_shift_pool_dir
else:
    from .annotate_gates import read_pool
    from .card_copy import refuses_auto_publish
    from .editorial_zh import edit_pair, reader_lines, visitor_ready
    from .force_p0 import content_flags
    from .generate_derived import safe_http_url
    from .ingest_x import SHANGHAI, IngestError, parse_utc
    from .prompt_guard import find_instruction_override, strip_raw_post_fields
    from .score_pool import is_official_row, is_practice_row, load_score_config
    from .shift_ingest_x_to_pool import assert_shift_pool_dir

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
TOPIC_SLUG = "hands-on"
TOPIC = {
    "slug": TOPIC_SLUG,
    "name": "跟着做",
    "track": "build",
    "summary": "把能照着做的步骤收在一处，下次遇到同类问题时可以直接翻出来。",
    "audience": "想自己动手试一遍的人",
    "tools": [],
    "playbook": [],
    "pitfalls": ["动手前对照原文核对命令、授权和费用。"],
}
CAUTION = "动手前对照原文核对命令、授权和费用。这里没有替你跑过这组步骤。"
STEP_SPLIT = re.compile(r"\n+|；")
STEP_MARK = re.compile(r"^\s*(?:\d+[\.、\)]\s*|首先|然后|接着|最后)\s*")


def _clock(row: dict) -> datetime | None:
    for key in ("published_at", "ingested_at"):
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            try:
                return parse_utc(raw)
            except IngestError:
                continue
    return None


def _day(row: dict) -> str:
    clock = _clock(row)
    if clock is None:
        return ""
    return clock.astimezone(SHANGHAI).strftime("%Y-%m-%d")


def _suffix(row: dict) -> str:
    return str(row.get("id") or "").rsplit("-", 1)[-1].lower()


def _plain_bits(row: dict) -> str:
    parts = []
    for key in ("title", "snippet"):
        value = row.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def extract_steps(text: str) -> list[str]:
    """Keep numbered or sequenced sentences. A title plus a remark is not a tutorial."""
    steps: list[str] = []
    for chunk in STEP_SPLIT.split(text or ""):
        for sentence in re.split(r"。", chunk):
            raw = sentence.strip()
            if not STEP_MARK.match(raw):
                continue
            cleaned = STEP_MARK.sub("", sentence).strip(" ，,;；")
            if not cleaned or find_instruction_override(cleaned):
                continue
            if not visitor_ready(cleaned):
                continue
            steps.append(cleaned if cleaned.endswith("。") else cleaned + "。")
            if len(steps) >= 8:
                return steps
    return steps


def kind_of(text: str) -> str:
    if re.search(r"变现|报价|接单|收费", text):
        return "变现"
    if re.search(r"硬件|电路|开发板", text):
        return "硬件"
    if re.search(r"视频|音乐|绘画|海报", text):
        return "创意作品"
    if re.search(r"工作流|技能", text, re.I):
        return "Skill / 工作流"
    return "工具用法"


def _cold(row: dict, review_min: float) -> bool:
    status = row.get("status_in_pool")
    if status in {"dropped", "pending", "rerouted"}:
        return True
    if row.get("prefilter") not in {None, "PASS"} and row.get("prefilter") != "PASS":
        return True
    if row.get("prefilter") == "BLOCK":
        return True
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    if score.get("band") == "drop" or score.get("band_reason") == "drop_low_score":
        return True
    try:
        value = float(score.get("value"))
    except (TypeError, ValueError):
        value = None
    if value is not None and value < review_min and not refuses_auto_publish(row):
        return True
    return False


def _handle(row: dict) -> str:
    handle = (row.get("source") or {}).get("handle")
    if isinstance(handle, str) and handle.strip():
        return handle.strip().lstrip("@")
    return ""


def project_practice(row: dict, practice_handles: set[str], review_min: float) -> dict | None:
    if not is_practice_row(row, practice_handles):
        return None
    if refuses_auto_publish(row):
        return None
    if _cold(row, review_min):
        return None
    if row.get("status_in_pool") not in {None, "active", "deferred"}:
        return None
    day = _day(row)
    suffix = _suffix(row)
    if not day or not re.fullmatch(r"[a-f0-9]{12}", suffix):
        return None
    steps = extract_steps(_plain_bits(row))
    if len(steps) < 2:
        return None
    url = row.get("url_norm") or row.get("url") or ""
    if not safe_http_url(url):
        return None
    raw_title = row.get("title") if isinstance(row.get("title"), str) else ""
    edited = edit_pair(raw_title, steps[0].rstrip("。"))
    if not edited:
        title = raw_title.strip()
        if not visitor_ready(title):
            return None
    else:
        title = edited[0]
    if find_instruction_override(title):
        return None
    handle = _handle(row) or "作者"
    takeaway = steps[0] if len(steps[0]) <= 240 else steps[0][:239] + "…"
    card = {
        "id": f"prac-{day.replace('-', '')}-{suffix}",
        "kind": kind_of(_plain_bits(row)),
        "title": title[:120],
        "author": handle[:80],
        "url": url,
        "time": _clock(row).astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M") if _clock(row) else day,
        "takeaway": takeaway,
        "steps": steps,
        "caution": CAUTION,
        "difficulty": "入门" if len(steps) <= 4 else "进阶",
        "prerequisites": ["原文里用到的账号或软件"],
        "estimated_time": "按步骤做完",
        "verified": False,
        "candidate_id": row.get("id"),
    }
    cleaned = strip_raw_post_fields(card)
    if not visitor_ready(cleaned["title"]) or not visitor_ready(cleaned["takeaway"]):
        return None
    return cleaned


def project_watch(row: dict, practice_handles: set[str], review_min: float) -> dict | None:
    if is_practice_row(row, practice_handles):
        return None
    if refuses_auto_publish(row):
        return None
    if _cold(row, review_min):
        return None
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    if score.get("band") == "auto_brief" or (score.get("official_source") and is_official_row(row)):
        return None
    flags = content_flags(row)
    role = (row.get("source") or {}).get("role_guess")
    if flags.get("content_type") != "analysis" and role != "analysis":
        return None
    if flags.get("tutorial") and len(extract_steps(_plain_bits(row))) >= 2:
        return None
    day = _day(row)
    suffix = _suffix(row)
    if not day or not re.fullmatch(r"[a-f0-9]{12}", suffix):
        return None
    url = row.get("url_norm") or row.get("url") or ""
    if not safe_http_url(url):
        return None
    raw_title = row.get("title") if isinstance(row.get("title"), str) else ""
    raw_summary = row.get("snippet") if isinstance(row.get("snippet"), str) else ""
    edited = edit_pair(raw_title, raw_summary)
    if not edited:
        return None
    title, summary = edited
    why, affect = reader_lines("赛道")
    if find_instruction_override(title) or find_instruction_override(summary):
        return None
    return {
        "id": f"watch-{day.replace('-', '')}-{suffix}",
        "date": day,
        "title": title[:120],
        "summary": summary[:240],
        "why": why,
        "affect": affect,
        "url": url,
        "source": _handle(row) or "来源",
        "candidate_id": row.get("id"),
    }


def _load(path: Path, fallback: dict) -> dict:
    if not path.is_file():
        return json.loads(json.dumps(fallback))
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_projections(
    practice_cards: list[dict],
    watch_items: list[dict],
    *,
    inbox: Path,
    atlas_path: Path,
    suggestions_path: Path,
    watch_path: Path,
) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    for card in practice_cards:
        target = inbox / f"{card['id']}.json"
        if not target.is_file():
            _write(target, card)
    if practice_cards:
        atlas = _load(
            atlas_path,
            {
                "schema_version": 1,
                "snapshot": "2026-10-23",
                "note": "五个方向仍在。主题、原帖和博主从 2026-10-23 起重新收录。没有素材的主题不写入本文件。",
                "tracks": [],
                "topics": [],
                "sources": [],
                "creators": [],
            },
        )
        topics = [item for item in atlas.get("topics") or [] if isinstance(item, dict)]
        if not any(item.get("slug") == TOPIC_SLUG for item in topics):
            topics.append(dict(TOPIC))
        atlas["topics"] = topics
        sources = [item for item in atlas.get("sources") or [] if isinstance(item, dict)]
        seen = {str(item.get("id") or "") for item in sources}
        for card in practice_cards:
            if card["id"] in seen:
                continue
            sources.append(
                {
                    "id": card["id"],
                    "url": card["url"],
                    "author": card["author"],
                    "topic": TOPIC_SLUG,
                    "type": "教程",
                    "title": card["title"],
                    "excerpt": card["takeaway"][:500],
                    "date": card["time"][:10],
                    "origin": "practice",
                    "verified": False,
                }
            )
        atlas["sources"] = sources
        _write(atlas_path, atlas)
        suggestions = _load(
            suggestions_path,
            {
                "schema_version": 1,
                "generated_at": "2026-10-24T00:00:00Z",
                "note": "每条做法对应一个主题建议。还没经人确认的，不会改写主题手册正文。",
                "items": [],
            },
        )
        items = [item for item in suggestions.get("items") or [] if isinstance(item, dict)]
        have = {str(item.get("id") or "") for item in items}
        for card in practice_cards:
            if card["id"] in have:
                continue
            items.append(
                {
                    "id": card["id"],
                    "topic": TOPIC_SLUG,
                    "reason": "这条写清了可照着做的步骤，先归在跟着做。确认之前不改手册正文。",
                    "verified": False,
                    "apply": "blocked_unverified",
                    "lane": "跟着做",
                }
            )
        suggestions["items"] = items
        suggestions["note"] = "每条做法对应一个主题建议。还没经人确认的，不会改写主题手册正文。"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", str(suggestions.get("generated_at") or "")):
            suggestions["generated_at"] = "2026-10-24T00:00:00Z"
        _write(suggestions_path, suggestions)
    watch_doc = _load(
        watch_path,
        {
            "schema_version": 1,
            "updated": None,
            "note": "跨过一天仍然值得跟踪的领域进展。写不清价值的不会出现在这里。",
            "items": [],
        },
    )
    current = [item for item in watch_doc.get("items") or [] if isinstance(item, dict)]
    by_id = {str(item.get("id") or ""): item for item in current}
    order = [str(item.get("id") or "") for item in current]
    for item in watch_items:
        if item["id"] not in by_id:
            order.append(item["id"])
        by_id[item["id"]] = item
    watch_doc["items"] = [by_id[key] for key in order if key in by_id]
    watch_doc["note"] = "跨过一天仍然值得跟踪的领域进展。写不清价值的不会出现在这里。"
    if not watch_items and watch_path.is_file():
        return
    if watch_items:
        watch_doc["updated"] = datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M 北京时间")
    _write(watch_path, watch_doc)


def project_rows(rows: list[dict], practice_handles: set[str], review_min: float) -> tuple[list[dict], list[dict]]:
    practice = []
    watch = []
    seen_p: set[str] = set()
    seen_w: set[str] = set()
    for row in rows:
        card = project_practice(row, practice_handles, review_min)
        if card and card["id"] not in seen_p:
            seen_p.add(card["id"])
            practice.append(card)
            continue
        item = project_watch(row, practice_handles, review_min)
        if item and item["id"] not in seen_w:
            seen_w.add(item["id"])
            watch.append(item)
    return practice, watch


def _sample_row(**extra) -> dict:
    base = {
        "schema_version": 1,
        "id": "cand-20261024-abc123abc123",
        "url": "https://x.com/op7418/status/77001",
        "url_norm": "https://x.com/op7418/status/77001",
        "published_at": "2026-10-24T01:00:00Z",
        "ingested_at": "2026-10-24T02:00:00Z",
        "source": {"channel": "x", "handle": "op7418", "role_guess": None},
        "tier_prior": "practice",
        "participation": "practice",
        "lane_hint": "practice",
        "prefilter": "PASS",
        "status_in_pool": "active",
        "score": {"band": "review", "band_reason": "review_practice", "value": 0.61},
        "title": "用三步把本地模型接到你的编辑器",
        "snippet": "首先安装官方命令行并登录自己的账号。然后在编辑器里填上本地服务地址。接着用一条真实任务跑通。",
    }
    base.update(extra)
    return base


def self_check() -> None:
    import tempfile

    handles = {"op7418"}
    practice, watch = project_rows([_sample_row()], handles, 0.34)
    if len(practice) != 1 or watch:
        raise SystemExit(f"FAIL: step tutorial did not land on practice {practice} {watch}")
    card = practice[0]
    if len(card["steps"]) < 2 or card["verified"] is not False:
        raise SystemExit("FAIL: practice card shape")
    if "snippet" in card or "status_in_pool" in card:
        raise SystemExit("FAIL: pool fields reached the practice card")
    english = _sample_row(
        id="cand-20261024-abc123abc124",
        title="How to install the local model",
        snippet="First install the CLI. Then paste the endpoint. Finally run a task.",
    )
    if project_practice(english, handles, 0.34) is not None:
        raise SystemExit("FAIL: English tutorial was published")
    cold = _sample_row(id="cand-20261024-abc123abc125", score={"band": "drop", "band_reason": "drop_low_score", "value": 0.1})
    if project_practice(cold, handles, 0.34) is not None:
        raise SystemExit("FAIL: low-score tutorial was published")
    forced = _sample_row(
        id="cand-20261024-abc123abc126",
        force_p0={"active": True, "kinds": ["frontier_launch"]},
        score={"band": "review", "band_reason": "review_p0", "value": 0.8},
    )
    if project_practice(forced, handles, 0.34) is not None:
        raise SystemExit("FAIL: pick-queue row became a practice card")
    thin = _sample_row(id="cand-20261024-abc123abc127", snippet="只写了一句感想，没有步骤。")
    if project_practice(thin, handles, 0.34) is not None:
        raise SystemExit("FAIL: a note without steps became a practice card")
    analysis = _sample_row(
        id="cand-20261024-abc123abc128",
        url="https://example.com/analysis-horizon",
        url_norm="https://example.com/analysis-horizon",
        tier_prior="T2",
        participation=None,
        lane_hint=None,
        source={"channel": "x", "handle": "analyst", "role_guess": "analysis"},
        title="开源模型的成本曲线还会再降一个台阶",
        snippet="从公开报价看，同等能力的开源模型调用成本还会继续下降，适合按季度重新做一次选型。",
        score={"band": "review", "band_reason": "review_score", "value": 0.5, "official_source": False},
    )
    projected_watch = project_watch(analysis, handles, 0.34)
    if not projected_watch or projected_watch["id"].startswith("prac-"):
        raise SystemExit(f"FAIL: analysis did not become a watch item {projected_watch}")
    if project_watch(analysis | {"score": {"band": "auto_brief", "official_source": True, "value": 0.8}}, handles, 0.34):
        raise SystemExit("FAIL: news brief also became a watch item")
    brief_practice, brief_watch = project_rows([analysis], handles, 0.34)
    if brief_practice or not brief_watch:
        raise SystemExit("FAIL: analysis leaked into practice")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        apply_projections(
            practice,
            brief_watch,
            inbox=root / "inbox",
            atlas_path=root / "atlas.source.json",
            suggestions_path=root / "topic-suggestions.json",
            watch_path=root / "watch.json",
        )
        written = json.loads((root / "inbox" / f"{card['id']}.json").read_text(encoding="utf-8"))
        if written["id"] != card["id"]:
            raise SystemExit("FAIL: inbox write")
        atlas = json.loads((root / "atlas.source.json").read_text(encoding="utf-8"))
        if card["id"] not in {item["id"] for item in atlas["sources"]}:
            raise SystemExit("FAIL: practice card was not mapped onto a topic")
        suggestions = json.loads((root / "topic-suggestions.json").read_text(encoding="utf-8"))
        if suggestions["items"][0]["apply"] != "blocked_unverified":
            raise SystemExit("FAIL: unverified practice was marked ready to rewrite the handbook")
        watch_doc = json.loads((root / "watch.json").read_text(encoding="utf-8"))
        if watch_doc["items"][0]["id"] != projected_watch["id"]:
            raise SystemExit("FAIL: watch file")
    print("OK project_public_lanes self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project practice and watch cards from a private pool.")
    parser.add_argument("--pool-dir")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not args.pool_dir:
        parser.error("pass --pool-dir or --self-check")
    pool = Path(args.pool_dir)
    assert_shift_pool_dir(pool)
    cfg = load_score_config(ROOT)
    handles = {item.lower() for item in json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("practice_handles") or []}
    rows = [row for _day, row in read_pool(pool)]
    practice, watch = project_rows(rows, handles, cfg.review_min)
    apply_projections(
        practice,
        watch,
        inbox=PUBLIC / "practice" / "inbox",
        atlas_path=PUBLIC / "data" / "atlas.source.json",
        suggestions_path=PUBLIC / "data" / "topic-suggestions.json",
        watch_path=PUBLIC / "data" / "watch.json",
    )
    print(f"OK project_public_lanes: practice={len(practice)} watch={len(watch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
