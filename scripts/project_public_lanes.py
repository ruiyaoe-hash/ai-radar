#!/usr/bin/env python3
"""Place finished public cards for 实战手册 and 专题观察.

Shifts call this after scoring. A practice-lane row that clears both gates
already in the repo becomes one practice card under public/practice/inbox/:

  - can-follow-along: at least two finished Chinese steps
  - engagement: bookmarks at least config score.bookmark_prior

generate_derived.py then merges that inbox into practice.json. The same run
writes a watch item for a long-horizon analysis that is not a practice row,
not a news brief, and not a pick. Verified stays false. Re-running does not
duplicate an inbox file or a watch id.

An X post often has an empty title and a usable body. The first usable
sentence becomes a provisional title before the Chinese editorial layer, so
a qualifying row is not dropped only because title is blank. English or
unfinished copy still does not publish. Nothing here writes briefs.

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
    from score_pool import _count, is_official_row, is_practice_row, load_score_config
    from shift_ingest_x_to_pool import assert_shift_pool_dir
else:
    from .annotate_gates import read_pool
    from .card_copy import refuses_auto_publish
    from .editorial_zh import edit_pair, reader_lines, visitor_ready
    from .force_p0 import content_flags
    from .generate_derived import safe_http_url
    from .ingest_x import SHANGHAI, IngestError, parse_utc
    from .prompt_guard import find_instruction_override, strip_raw_post_fields
    from .score_pool import _count, is_official_row, is_practice_row, load_score_config
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
_STEP_WORD = r"第[0-9一二三四五六七八九十]+步|首先|然后|接着|最后|其次|下一步"
_STEP_NUM = r"(?<!\d)\d+[\.、\)](?!\d)"
# Numbered steps may sit mid-paragraph ("1. … 2. …"). Sequence words only
# count at a sentence boundary, so ordinary prose is not sliced into steps.
_STEP_BOUNDARY = re.compile(
    rf"(?:^|[\n；;。])\s*(?:{_STEP_NUM}|{_STEP_WORD})\s*[:：]?"
    rf"|(?<=\s)(?:{_STEP_NUM}|第[0-9一二三四五六七八九十]+步)\s*[:：]?"
)
_SENTENCE_SPLIT = re.compile(r"[。！？!?\n；;]+")
_LEAD_MARK = re.compile(
    rf"^\s*(?:{_STEP_NUM}|{_STEP_WORD})\s*[:：]?\s*"
)
_URL = re.compile(r"https?://\S+")


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


def _marker_spans(text: str) -> list[re.Match[str]]:
    found = list(_STEP_BOUNDARY.finditer(text or ""))
    found.sort(key=lambda match: (match.start(), -match.end()))
    kept: list[re.Match[str]] = []
    last_end = -1
    for match in found:
        if match.start() < last_end:
            continue
        kept.append(match)
        last_end = match.end()
    return kept


def extract_steps(text: str) -> list[str]:
    """Keep numbered or sequenced sentences. A title plus a remark is not a tutorial.

    This is the can-follow-along gate. Each kept step is finished Chinese.
    A short reply, or a single numbered line, does not qualify.
    """
    raw = text or ""
    matches = _marker_spans(raw)
    steps: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        piece = _SENTENCE_SPLIT.split(raw[match.end() : end], maxsplit=1)[0]
        cleaned = piece.strip(" ，,;；:：。 \t")
        if not cleaned or find_instruction_override(cleaned):
            continue
        if not visitor_ready(cleaned):
            continue
        steps.append(cleaned if cleaned.endswith("。") else cleaned + "。")
        if len(steps) >= 8:
            return steps
    return steps


def first_usable_sentence(text: str) -> str:
    """First sentence that can stand in for an empty title, before editorial."""
    stripped = _URL.sub(" ", text or "")
    for part in _SENTENCE_SPLIT.split(stripped):
        sentence = _LEAD_MARK.sub("", part)
        sentence = re.sub(r"\s+", " ", sentence).strip(" ，,;；:：")
        if len(sentence) < 8 or find_instruction_override(sentence):
            continue
        return sentence[:120]
    return ""


def passes_engagement_gate(row: dict, bookmark_min: float) -> bool:
    """Saves must clear score.bookmark_prior. Missing counts do not pass.

    The prior is the engagement floor already in config.json. A liked reply
    with no bookmarks stays in the pool.
    """
    engagement = row.get("engagement")
    if not isinstance(engagement, dict):
        return False
    if "bookmarks" not in engagement and "likes" not in engagement:
        return False
    return _count(engagement.get("bookmarks")) + 1e-9 >= float(bookmark_min)


def _raw_title(row: dict) -> str:
    title = row.get("title") if isinstance(row.get("title"), str) else ""
    return title.strip()


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


def project_practice(
    row: dict,
    practice_handles: set[str],
    review_min: float,
    bookmark_min: float,
) -> dict | None:
    if not is_practice_row(row, practice_handles):
        return None
    if refuses_auto_publish(row):
        return None
    if _cold(row, review_min):
        return None
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    if score.get("band") != "review":
        return None
    if row.get("status_in_pool") not in {None, "active", "deferred"}:
        return None
    if not passes_engagement_gate(row, bookmark_min):
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
    raw_title = _raw_title(row)
    if not raw_title:
        raw_title = first_usable_sentence(_plain_bits(row)) or steps[0].rstrip("。")
    summary = steps[0].rstrip("。")
    edited = edit_pair(raw_title, summary)
    if not edited:
        return None
    title, summary = edited
    if find_instruction_override(title) or find_instruction_override(summary):
        return None
    handle = _handle(row) or "作者"
    takeaway = summary if len(summary) <= 240 else summary[:239] + "…"
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
    raw_title = _raw_title(row)
    raw_summary = row.get("snippet") if isinstance(row.get("snippet"), str) else ""
    raw_summary = raw_summary.strip()
    if not raw_title:
        raw_title = first_usable_sentence(raw_summary) or first_usable_sentence(_plain_bits(row))
    if not raw_title or not raw_summary:
        return None
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


def project_rows(
    rows: list[dict],
    practice_handles: set[str],
    review_min: float,
    bookmark_min: float,
) -> tuple[list[dict], list[dict]]:
    practice = []
    watch = []
    seen_p: set[str] = set()
    seen_w: set[str] = set()
    for row in rows:
        card = project_practice(row, practice_handles, review_min, bookmark_min)
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
        "engagement": {"likes": 12, "bookmarks": 8, "captured_at": "2026-10-24T02:00:00Z"},
    }
    base.update(extra)
    return base


def self_check() -> None:
    import tempfile

    handles = {"op7418"}
    floor = 3.0
    practice, watch = project_rows([_sample_row()], handles, 0.34, floor)
    if len(practice) != 1 or watch:
        raise SystemExit(f"FAIL: step tutorial did not land on practice {practice} {watch}")
    card = practice[0]
    if len(card["steps"]) < 2 or card["verified"] is not False:
        raise SystemExit("FAIL: practice card shape")
    if "snippet" in card or "status_in_pool" in card:
        raise SystemExit("FAIL: pool fields reached the practice card")
    if not visitor_ready(card["title"]) or not visitor_ready(card["takeaway"]):
        raise SystemExit("FAIL: practice card is not finished Chinese")
    english = _sample_row(
        id="cand-20261024-abc123abc124",
        title="How to install the local model",
        snippet="First install the CLI. Then paste the endpoint. Finally run a task.",
    )
    if project_practice(english, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: English tutorial was published")
    cold = _sample_row(id="cand-20261024-abc123abc125", score={"band": "drop", "band_reason": "drop_low_score", "value": 0.1})
    if project_practice(cold, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: low-score tutorial was published")
    forced = _sample_row(
        id="cand-20261024-abc123abc126",
        force_p0={"active": True, "kinds": ["frontier_launch"]},
        score={"band": "review", "band_reason": "review_p0", "value": 0.8},
    )
    if project_practice(forced, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: pick-queue row became a practice card")
    thin = _sample_row(id="cand-20261024-abc123abc127", snippet="只写了一句感想，没有步骤。")
    if project_practice(thin, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a note without steps became a practice card")
    blank = _sample_row(
        id="cand-20261024-abc123abc129",
        title="",
        snippet="首先安装官方命令行并登录自己的账号。然后在编辑器里填上本地服务地址。接着用一条真实任务跑通。",
    )
    blank_card = project_practice(blank, handles, 0.34, floor)
    if not blank_card or not visitor_ready(blank_card["title"]):
        raise SystemExit(f"FAIL: empty title dropped a finished step list {blank_card}")
    if re.search(r"[A-Za-z]{4,}", blank_card["title"]):
        raise SystemExit("FAIL: empty title published an English headline")
    inline = _sample_row(
        id="cand-20261024-abc123abc12a",
        title=None,
        snippet="1. 安装官方命令行并登录自己的账号 2. 在编辑器里填上本地服务地址 3. 用一条真实任务把流程跑通",
    )
    inline_card = project_practice(inline, handles, 0.34, floor)
    if not inline_card or len(inline_card["steps"]) < 2:
        raise SystemExit(f"FAIL: inline numbered steps were dropped {inline_card}")
    quiet = _sample_row(
        id="cand-20261024-abc123abc12b",
        engagement={"likes": 40, "bookmarks": 0, "captured_at": "2026-10-24T02:00:00Z"},
    )
    if project_practice(quiet, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a reply with no bookmarks became a practice card")
    unsaved = _sample_row(id="cand-20261024-abc123abc12c")
    unsaved.pop("engagement", None)
    if project_practice(unsaved, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a row with no engagement counts became a practice card")
    short = _sample_row(
        id="cand-20261024-abc123abc12d",
        snippet="1. 点保存 2. 再点一次",
    )
    if project_practice(short, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a thin two-liner became a practice card")
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
    blank_watch = project_watch(analysis | {"id": "cand-20261024-abc123abc12e", "title": ""}, handles, 0.34)
    if not blank_watch or not visitor_ready(blank_watch["title"]) or not visitor_ready(blank_watch["summary"]):
        raise SystemExit(f"FAIL: empty-title analysis did not become a Chinese watch card {blank_watch}")
    if not blank_watch.get("source") or not blank_watch.get("url"):
        raise SystemExit("FAIL: watch card dropped 背景与出处")
    english_watch = project_watch(
        analysis
        | {
            "id": "cand-20261024-abc123abc12f",
            "title": "",
            "snippet": "Costs keep falling and teams should revisit the model choice next quarter.",
        },
        handles,
        0.34,
    )
    if english_watch is not None:
        raise SystemExit("FAIL: English analysis was published onto 专题观察")
    brief_practice, brief_watch = project_rows([analysis], handles, 0.34, floor)
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
        apply_projections(
            practice,
            brief_watch,
            inbox=root / "inbox",
            atlas_path=root / "atlas.source.json",
            suggestions_path=root / "topic-suggestions.json",
            watch_path=root / "watch.json",
        )
        inbox_files = list((root / "inbox").glob("*.json"))
        if len(inbox_files) != 1:
            raise SystemExit(f"FAIL: re-run duplicated practice inbox {inbox_files}")
        atlas_again = json.loads((root / "atlas.source.json").read_text(encoding="utf-8"))
        if sum(1 for item in atlas_again["sources"] if item["id"] == card["id"]) != 1:
            raise SystemExit("FAIL: re-run duplicated the practice source")
        watch_again = json.loads((root / "watch.json").read_text(encoding="utf-8"))
        if sum(1 for item in watch_again["items"] if item["id"] == projected_watch["id"]) != 1:
            raise SystemExit("FAIL: re-run duplicated the watch item")
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
    practice, watch = project_rows(rows, handles, cfg.review_min, cfg.bookmark_prior)
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
