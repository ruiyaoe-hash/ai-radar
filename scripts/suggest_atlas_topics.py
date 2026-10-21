#!/usr/bin/env python3
"""Suggest an atlas topic for practice-lane candidates. Do not publish them.

Practice lane means a public practice card, or a pool row that is
practice_handles / tier_prior=practice / lane_hint or participation
practice / score.band_reason=review_practice. Dropped rows and auto_brief
rows are not suggestions. auto_brief never receives a practice row (B).

Matching uses tool names already on the atlas topic. The reason names the
tool and the topic. It does not copy snippet or steps.

  python3 scripts/suggest_atlas_topics.py --self-check
  python3 scripts/suggest_atlas_topics.py
  python3 scripts/suggest_atlas_topics.py --pool-dir ../ai-radar-pool

A suggestion with verified=false stays blocked. Writing the handbook takes
an explicit confirm file, and the public practice card must already say
verified=true. The script never flips that flag and never pastes steps.

  python3 scripts/suggest_atlas_topics.py --apply confirm.json
  python3 scripts/generate_derived.py

confirm.json:

    {"items": [
      {"id": "prac-...", "topic": "agent-skills", "verified": true,
       "playbook": {"title": "人写的一步", "detail": "人写的一句，不贴原文步骤"}}
    ]}

playbook is optional. Without it, a verified confirm only ensures the
source row (excerpt = takeaway). With it, the handbook gains that one
human sentence.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from annotate_gates import read_pool, write_pool
    from card_times import utc_now_iso
    from generate_derived import safe_http_url
    from ingest_x import IngestError, assert_not_public, dumps_record
    from score_pool import is_practice_row
    from shift_ingest_x_to_pool import assert_shift_pool_dir
else:
    from .annotate_gates import read_pool, write_pool
    from .card_times import utc_now_iso
    from .generate_derived import safe_http_url
    from .ingest_x import IngestError, assert_not_public, dumps_record
    from .score_pool import is_practice_row
    from .shift_ingest_x_to_pool import assert_shift_pool_dir

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
NOTE = "建议清单。held 还要人工确认；blocked_unverified 不能写手册；no_topic 要人指定主题。这里不是上站。"
KIND_TYPE = {
    "工具用法": "教程",
    "Skill / 工作流": "方法论",
    "创意作品": "实战项目",
    "变现": "方法论",
    "硬件": "实战项目",
}
LANE_PREFIX = {
    "review_practice": "分档 review_practice。",
    "practice_handles": "账号在 practice_handles。",
    "tier_prior": "tier_prior=practice。",
    "lane_hint": "车道标成 practice。",
    "public_practice": "",
}


class ApplyError(Exception):
    pass


def _handles(root: Path | None = None) -> set[str]:
    cfg = json.loads(((root or ROOT) / "config.json").read_text(encoding="utf-8"))
    return {str(item).strip().lower() for item in (cfg.get("practice_handles") or []) if str(item).strip()}


def _needle_hit(needle: str, text: str) -> bool:
    if re.search(r"[A-Za-z0-9]", needle):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])"
        return re.search(pattern, text, re.I) is not None
    return needle.casefold() in text.casefold()


def match_topics(text: str, topics: list[dict]) -> dict:
    """Best tool-name hit. A tie leaves topic null so a person picks."""
    scores: dict[str, int] = {}
    best_tool: dict[str, str] = {}
    for topic in topics:
        slug = str(topic.get("slug") or "")
        if not slug:
            continue
        score = 0
        winner: tuple[int, str] | None = None
        for tool in topic.get("tools") or []:
            name = str(tool).strip()
            if len(name) < 2 or not _needle_hit(name, text):
                continue
            weight = 5 + len(name)
            score += weight
            if winner is None or weight > winner[0] or (weight == winner[0] and len(name) > len(winner[1])):
                winner = (weight, name)
        if score and winner:
            scores[slug] = score
            best_tool[slug] = winner[1]
    if not scores:
        return {"topic": None, "tool": None, "tied": []}
    ranked = sorted(scores, key=lambda slug: (-scores[slug], -len(best_tool[slug]), slug))
    top = ranked[0]
    if len(ranked) > 1 and scores[ranked[1]] == scores[top]:
        tied = [slug for slug in ranked if scores[slug] == scores[top]]
        return {"topic": None, "tool": None, "tied": tied}
    return {"topic": top, "tool": best_tool[top], "tied": []}


def _apply_state(verified: bool, topic: str | None) -> str:
    if not topic:
        return "no_topic"
    if not verified:
        return "blocked_unverified"
    return "held"


def _tie_list(slugs: list[str]) -> str:
    if len(slugs) <= 3:
        return "、".join(slugs)
    return f"{slugs[0]}、{slugs[1]} 等 {len(slugs)} 个主题"


def _clip(reason: str) -> str:
    reason = re.sub(r"\s+", " ", reason).strip()
    if len(reason) <= 240:
        return reason
    return reason[:239] + "…"


def _names(topics: list[dict]) -> dict[str, str]:
    return {str(item.get("slug") or ""): str(item.get("name") or item.get("slug") or "") for item in topics}


def build_reason(
    *,
    existing: str | None,
    match: dict,
    verified: bool,
    names: dict[str, str],
    lane: str,
) -> tuple[str | None, str]:
    chosen = existing or (None if match["tied"] else match["topic"])
    bits = []
    prefix = LANE_PREFIX.get(lane, "")
    if prefix:
        bits.append(prefix)
    if existing:
        bits.append(f"已在图谱归入 {existing}（{names.get(existing, existing)}）。")
        if match["tied"]:
            bits.append("工具名同时对上 " + _tie_list(match["tied"]) + "，未确认前不改归属。")
        elif match["topic"] and match["topic"] != existing:
            bits.append(f"按工具名也会落到 {match['topic']}，未确认前不改归属。")
        elif match["tool"]:
            bits.append(f"工具名 {match['tool']} 也对上同一主题。")
    elif match["tied"]:
        bits.append("工具名同时对上 " + _tie_list(match["tied"]) + "，留给人工指定。")
    elif match["topic"]:
        tool = match["tool"] or "工具名"
        bits.append(f"工具名 {tool} 对上 {match['topic']}（{names.get(match['topic'], match['topic'])}）。")
    else:
        bits.append("没有对上现有主题的工具名，留给人工指定。")
    if verified:
        bits.append("verified=true。确认后才改手册，脚本不粘贴步骤。")
    else:
        bits.append("verified=false，不能当作已上站的完备课程，也不会写入手册。")
    return chosen, _clip("".join(bits))


def _suggestion(
    *,
    item_id: str,
    existing: str | None,
    match: dict,
    verified: bool,
    names: dict[str, str],
    lane: str,
) -> dict:
    topic, reason = build_reason(
        existing=existing, match=match, verified=verified, names=names, lane=lane
    )
    row = {
        "id": item_id,
        "topic": topic,
        "reason": reason,
        "verified": bool(verified),
        "apply": _apply_state(bool(verified), topic),
        "lane": lane,
    }
    matched: list[str] = []
    if existing:
        matched.append(f"atlas:{existing}")
    if match.get("tool") and match.get("topic") and not match.get("tied"):
        matched.append(f"tool:{match['tool']}")
    if matched:
        row["matched_on"] = matched[:8]
    return row


def practice_lane(row: dict, handles: set[str]) -> str | None:
    """Return a lane label, or None when this row is not a practice suggestion."""
    if row.get("status_in_pool") == "dropped" or row.get("drop_reason"):
        return None
    if row.get("prefilter") == "BLOCK":
        return None
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    band = score.get("band")
    if band in {"auto_brief", "drop"}:
        return None
    if score.get("band_reason") == "review_practice":
        return "review_practice"
    if not is_practice_row(row, handles):
        return None
    handle = str((row.get("source") or {}).get("handle") or "").strip().lower()
    if handle and handle in handles:
        return "practice_handles"
    if row.get("tier_prior") == "practice":
        return "tier_prior"
    return "lane_hint"


def _existing_topic(atlas: dict, item_id: str) -> str | None:
    for source in atlas.get("sources") or []:
        if isinstance(source, dict) and source.get("id") == item_id and source.get("topic"):
            return str(source["topic"])
    return None


def _practice_text(card: dict) -> str:
    parts = [card.get("title"), card.get("takeaway"), card.get("url"), card.get("kind"), card.get("author")]
    return "\n".join(str(part) for part in parts if isinstance(part, str))


def _pool_text(row: dict) -> str:
    handle = (row.get("source") or {}).get("handle") if isinstance(row.get("source"), dict) else ""
    parts = [row.get("title"), row.get("url"), row.get("url_norm"), handle, row.get("snippet")]
    return "\n".join(str(part) for part in parts if isinstance(part, str))


def load_practice_cards(public: Path) -> list[dict]:
    """Published practice.json, plus inbox cards not merged yet."""
    cards: dict[str, dict] = {}
    order: list[str] = []

    def _take(card: dict) -> None:
        item_id = str(card.get("id") or "")
        if not item_id or item_id in cards:
            return
        cards[item_id] = card
        order.append(item_id)

    path = public / "practice.json"
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        for item in doc.get("items") or []:
            if isinstance(item, dict):
                _take(item)
    inbox = public / "practice" / "inbox"
    if inbox.is_dir():
        for file in sorted(inbox.glob("*.json")):
            doc = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("id"):
                _take(doc)
            elif isinstance(doc, dict):
                for item in doc.get("items") or []:
                    if isinstance(item, dict):
                        _take(item)
    return [cards[item_id] for item_id in order]


def suggest_public(atlas: dict, cards: list[dict]) -> list[dict]:
    topics = [item for item in (atlas.get("topics") or []) if isinstance(item, dict)]
    names = _names(topics)
    rows = []
    for card in cards:
        item_id = str(card.get("id") or "")
        match = match_topics(_practice_text(card), topics)
        rows.append(
            _suggestion(
                item_id=item_id,
                existing=_existing_topic(atlas, item_id),
                match=match,
                verified=card.get("verified") is True,
                names=names,
                lane="public_practice",
            )
        )
    rows.sort(key=lambda item: item["id"])
    return rows


def suggest_pool(atlas: dict, pool_rows: list[dict], handles: set[str], cards: list[dict]) -> list[dict]:
    topics = [item for item in (atlas.get("topics") or []) if isinstance(item, dict)]
    names = _names(topics)
    verified_by_id = {str(card.get("id") or ""): card.get("verified") is True for card in cards}
    rows = []
    for row in pool_rows:
        lane = practice_lane(row, handles)
        if not lane:
            continue
        item_id = str(row.get("id") or "")
        archive_id = row.get("archive_id")
        existing = _existing_topic(atlas, str(archive_id)) if isinstance(archive_id, str) else None
        verified = verified_by_id.get(str(archive_id), False) if isinstance(archive_id, str) else False
        match = match_topics(_pool_text(row), topics)
        suggestion = _suggestion(
            item_id=item_id,
            existing=existing,
            match=match,
            verified=verified,
            names=names,
            lane=lane,
        )
        rows.append(suggestion)
    rows.sort(key=lambda item: item["id"])
    return rows


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def public_document(items: list[dict], generated_at: str) -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "note": NOTE,
        "items": items,
    }


def _author(card: dict) -> str:
    author = str(card.get("author") or "").strip()
    if "·" in author:
        author = author.split("·", 1)[0].strip()
    author = author.lstrip("@").strip()
    if not author:
        raise ApplyError(f"{card.get('id')} 缺少作者，不能写入图谱")
    return author[:80]


def _date(card: dict) -> str:
    raw = str(card.get("time") or card.get("date") or "")
    found = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if not found:
        raise ApplyError(f"{card.get('id')} 缺少日期，不能写入图谱")
    return found.group(1)


def _source_from_card(card: dict, topic: str) -> dict:
    url = safe_http_url(card.get("url") or "")
    if not url:
        raise ApplyError(f"{card.get('id')} 的链接不是 http(s)，不能写入图谱")
    title = str(card.get("title") or "").strip()
    excerpt = str(card.get("takeaway") or "").strip()
    if not title or not excerpt:
        raise ApplyError(f"{card.get('id')} 缺少标题或 takeaway，不会改用 steps 充正文")
    return {
        "id": str(card["id"]),
        "url": url,
        "author": _author(card),
        "topic": topic,
        "type": KIND_TYPE.get(str(card.get("kind") or ""), "教程"),
        "title": title[:160],
        "excerpt": excerpt[:500],
        "date": _date(card),
        "origin": "practice",
        "verified": True,
    }


def _steps_leaked(card: dict, detail: str) -> bool:
    for step in card.get("steps") or []:
        if isinstance(step, str) and len(step) >= 40 and step in detail:
            return True
    return False


def apply_confirmations(atlas: dict, cards: list[dict], confirm_items: list[dict]) -> dict:
    """Return a new atlas. Raises ApplyError without writing when any item is refused."""
    by_id = {str(card.get("id") or ""): card for card in cards}
    out = copy.deepcopy(atlas)
    topics = {str(item.get("slug") or ""): item for item in (out.get("topics") or []) if isinstance(item, dict)}
    sources = out.setdefault("sources", [])
    if not isinstance(sources, list):
        raise ApplyError("atlas sources 不是数组")
    index = {str(item.get("id") or ""): item for item in sources if isinstance(item, dict)}
    for entry in confirm_items:
        if not isinstance(entry, dict):
            raise ApplyError("确认项必须是对象")
        item_id = str(entry.get("id") or "")
        topic = str(entry.get("topic") or "")
        card = by_id.get(item_id)
        if not card:
            raise ApplyError(f"{item_id} 不在公开 practice.json 或 inbox，不能写入手册")
        if card.get("verified") is not True or entry.get("verified") is not True:
            raise ApplyError(f"{item_id} 未验证。verified 不是 true 时不写手册，也不假装已上站")
        if topic not in topics:
            raise ApplyError(f"{item_id} 的主题 {topic or '(空)'} 不在图谱里")
        fresh = _source_from_card(card, topic)
        current = index.get(item_id)
        if current is None:
            sources.append(fresh)
            index[item_id] = fresh
        else:
            if current.get("origin") not in {None, "practice"}:
                raise ApplyError(f"{item_id} 已是别的来源，不能改成实操")
            current["topic"] = topic
            current["origin"] = "practice"
            current["verified"] = True
        playbook = entry.get("playbook")
        if playbook is None:
            continue
        if not isinstance(playbook, dict):
            raise ApplyError(f"{item_id} 的 playbook 必须是人写的对象")
        title = str(playbook.get("title") or "").strip()
        detail = str(playbook.get("detail") or "").strip()
        if not title or not detail:
            raise ApplyError(f"{item_id} 的手册句要有 title 和 detail")
        if len(title) > 80 or len(detail) > 400:
            raise ApplyError(f"{item_id} 的手册句超长")
        if _steps_leaked(card, detail):
            raise ApplyError(f"{item_id} 的手册句整段贴了 steps，请改写成一句")
        topic_row = topics[topic]
        steps = topic_row.setdefault("playbook", [])
        if not isinstance(steps, list):
            raise ApplyError(f"{topic} playbook 不是数组")
        already = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            cites = step.get("sources") or []
            if step.get("title") == title and step.get("detail") == detail and item_id in cites:
                already = True
                break
        if not already:
            steps.append({"title": title, "detail": detail, "sources": [item_id]})
    return out


def _load_atlas(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise IngestError(f"{path}: expected an object")
    return data


def write_pool_suggestions(pool_dir: Path, suggestions: list[dict]) -> Path:
    assert_shift_pool_dir(pool_dir)
    by_id = {item["id"]: {key: value for key, value in item.items() if key != "id"} for item in suggestions}
    pairs = read_pool(pool_dir)
    rows = []
    for _path, row in pairs:
        item_id = str(row.get("id") or "")
        if item_id in by_id:
            row["atlas_suggestion"] = by_id[item_id]
        else:
            row.pop("atlas_suggestion", None)
        rows.append(row)
    if pairs:
        write_pool(pool_dir, pairs, rows)
    out = pool_dir / "suggestions" / "atlas-topics.jsonl"
    assert_not_public(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(dumps_record(item) + "\n" for item in suggestions)
    out.write_text(body, encoding="utf-8")
    return out


def self_check() -> None:
    """Fixtures only. Does not write the live atlas or a private pool."""
    sentinel = "SNIPPET-DO-NOT-COPY-9f3a"
    step = "UNIQUE_STEP_SENTINEL 这是一段超过四十个字的步骤，脚本不可以把它写进手册正文里。"
    topics = [
        {"slug": "ai-hardware", "name": "硬件", "tools": ["ESP32"]},
        {"slug": "model-gateway", "name": "网关", "tools": ["Magpie"]},
        {"slug": "agent-skills", "name": "Skills", "tools": ["llm", "Codex"]},
        {"slug": "ai-video", "name": "视频", "tools": ["Codex"]},
    ]
    atlas = {
        "topics": topics,
        "sources": [
            {"id": "prac-20261014-llm-file", "topic": "agent-skills", "origin": "practice"}
        ],
    }
    hardware = match_topics("用 ESP32 做终端", topics)
    if hardware["topic"] != "ai-hardware" or hardware["tool"] != "ESP32":
        raise SystemExit(f"FAIL: ESP32 match {hardware}")
    tied = match_topics("只写了 Codex", topics)
    if tied["topic"] is not None or "agent-skills" not in tied["tied"]:
        raise SystemExit(f"FAIL: Codex tie should stay unset {tied}")
    magpie = match_topics("跑 Magpie 网关", topics)
    if magpie["topic"] != "model-gateway":
        raise SystemExit(f"FAIL: Magpie match {magpie}")

    handles = {"vista8", "op7418"}
    rows = [
        {
            "id": "cand-20261021-aaaabbbbcccc",
            "title": "ESP32 入门",
            "snippet": sentinel,
            "url": "https://x.com/vista8/status/1",
            "source": {"channel": "x", "handle": "vista8", "role_guess": None},
            "tier_prior": "practice",
            "status_in_pool": "active",
            "drop_reason": None,
            "lane_hint": "practice",
        },
        {
            "id": "cand-20261021-bbbbccccdddd",
            "title": "跑 Magpie",
            "snippet": "别的正文",
            "source": {"channel": "x", "handle": "someone", "role_guess": None},
            "status_in_pool": "active",
            "score": {"band": "review", "band_reason": "review_practice"},
        },
        {
            "id": "cand-20261021-ccccddddeeee",
            "title": "ESP32 但是自动档",
            "source": {"channel": "x", "handle": "vista8", "role_guess": None},
            "status_in_pool": "active",
            "score": {"band": "auto_brief", "band_reason": "auto_primary"},
        },
        {
            "id": "cand-20261021-ddddeeeeffff",
            "title": "ESP32 步骤不够",
            "source": {"channel": "x", "handle": "vista8", "role_guess": None},
            "status_in_pool": "dropped",
            "drop_reason": "practice_not_steps",
        },
        {
            "id": "cand-20261021-eeeeffffaaaa",
            "title": "实验室发布",
            "source": {"channel": "x", "handle": "openai", "role_guess": "primary"},
            "tier_prior": "a_tier",
            "lane_hint": "digest",
            "status_in_pool": "active",
            "score": {"band": "review", "band_reason": "review_score"},
        },
        {
            "id": "cand-20261021-ffffaaaabbbb",
            "title": "只写了 Codex",
            "source": {"channel": "x", "handle": "op7418", "role_guess": None},
            "tier_prior": "practice",
            "status_in_pool": "active",
            "lane_hint": "practice",
        },
    ]
    pool_suggestions = suggest_pool(atlas, rows, handles, [])
    by_pool = {item["id"]: item for item in pool_suggestions}
    if set(by_pool) != {
        "cand-20261021-aaaabbbbcccc",
        "cand-20261021-bbbbccccdddd",
        "cand-20261021-ffffaaaabbbb",
    }:
        raise SystemExit(f"FAIL: pool lanes {set(by_pool)}")
    if by_pool["cand-20261021-aaaabbbbcccc"]["topic"] != "ai-hardware":
        raise SystemExit("FAIL: practice handle did not suggest ai-hardware")
    if by_pool["cand-20261021-bbbbccccdddd"]["lane"] != "review_practice":
        raise SystemExit("FAIL: review_practice lane missing")
    tied_row = by_pool["cand-20261021-ffffaaaabbbb"]
    if tied_row["topic"] is not None or tied_row["apply"] != "no_topic":
        raise SystemExit(f"FAIL: tied tools must stay no_topic {tied_row}")
    if sentinel in json.dumps(pool_suggestions, ensure_ascii=False):
        raise SystemExit("FAIL: suggestion copied the snippet")
    if any(item["apply"] == "held" and item["verified"] is False for item in pool_suggestions):
        raise SystemExit("FAIL: unverified pool row looked ready to apply")

    cards = [
        {
            "id": "prac-20261017-vista8-magpie",
            "title": "用 Docker 跑 Magpie",
            "takeaway": "一个入口转到多家模型。",
            "author": "vista8 · 指向 yetone/Magpie",
            "url": "https://x.com/vista8/status/2111488518577180866",
            "time": "2026-10-17 16:04",
            "kind": "工具用法",
            "verified": False,
            "steps": [step],
        },
        {
            "id": "prac-20261014-llm-file",
            "title": "用 llm 命令看文件",
            "takeaway": "先在命令行跑通。",
            "author": "Simon Willison",
            "url": "https://llm.datasette.io/en/stable/",
            "time": "2026-10-14 09:20",
            "kind": "工具用法",
            "verified": True,
            "steps": [step],
        },
    ]
    public_rows = suggest_public(atlas, cards)
    by_public = {item["id"]: item for item in public_rows}
    magpie_row = by_public["prac-20261017-vista8-magpie"]
    if magpie_row["topic"] != "model-gateway" or magpie_row["apply"] != "blocked_unverified":
        raise SystemExit(f"FAIL: unverified magpie suggestion {magpie_row}")
    if magpie_row["verified"] is not False:
        raise SystemExit("FAIL: suggestion flipped verified")
    llm_row = by_public["prac-20261014-llm-file"]
    if llm_row["topic"] != "agent-skills" or llm_row["apply"] != "held" or llm_row["verified"] is not True:
        raise SystemExit(f"FAIL: verified mapped card {llm_row}")
    if step in json.dumps(public_rows, ensure_ascii=False):
        raise SystemExit("FAIL: public suggestion copied steps")

    untouched = copy.deepcopy(atlas)
    try:
        apply_confirmations(
            atlas,
            cards,
            [{"id": "prac-20261017-vista8-magpie", "topic": "model-gateway", "verified": True}],
        )
    except ApplyError:
        pass
    else:
        raise SystemExit("FAIL: unverified card was written")
    if atlas != untouched:
        raise SystemExit("FAIL: refused apply mutated the atlas")

    try:
        apply_confirmations(
            atlas,
            cards,
            [{
                "id": "prac-20261014-llm-file",
                "topic": "agent-skills",
                "verified": True,
                "playbook": {"title": "人写的", "detail": step},
            }],
        )
    except ApplyError:
        pass
    else:
        raise SystemExit("FAIL: pasted steps became a playbook line")

    verified_cards = [dict(cards[0], verified=True), cards[1]]
    applied = apply_confirmations(
        atlas,
        verified_cards,
        [{"id": "prac-20261017-vista8-magpie", "topic": "model-gateway", "verified": True}],
    )
    written = json.dumps(applied, ensure_ascii=False)
    if step in written:
        raise SystemExit("FAIL: apply copied steps into the atlas")
    added = [item for item in applied["sources"] if item["id"] == "prac-20261017-vista8-magpie"]
    if len(added) != 1 or added[0]["origin"] != "practice" or added[0]["verified"] is not True:
        raise SystemExit(f"FAIL: source row {added}")
    if added[0]["excerpt"] != "一个入口转到多家模型。" or added[0]["author"] != "vista8":
        raise SystemExit(f"FAIL: source fields {added[0]}")
    if added[0]["topic"] != "model-gateway":
        raise SystemExit("FAIL: topic not written")
    if any(item.get("playbook") for item in applied["topics"]):
        raise SystemExit("FAIL: source-only confirm added a playbook")

    with_step = apply_confirmations(
        applied,
        verified_cards,
        [{
            "id": "prac-20261017-vista8-magpie",
            "topic": "model-gateway",
            "verified": True,
            "playbook": {"title": "人写的一步", "detail": "人写的一句，说明钥匙放在服务器上。"},
        }],
    )
    playbook = next(item["playbook"] for item in with_step["topics"] if item["slug"] == "model-gateway")
    if playbook != [{
        "title": "人写的一步",
        "detail": "人写的一句，说明钥匙放在服务器上。",
        "sources": ["prac-20261017-vista8-magpie"],
    }]:
        raise SystemExit(f"FAIL: playbook {playbook}")
    again = apply_confirmations(
        with_step,
        verified_cards,
        [{
            "id": "prac-20261017-vista8-magpie",
            "topic": "model-gateway",
            "verified": True,
            "playbook": {"title": "人写的一步", "detail": "人写的一句，说明钥匙放在服务器上。"},
        }],
    )
    again_steps = next(item["playbook"] for item in again["topics"] if item["slug"] == "model-gateway")
    if again_steps != playbook:
        raise SystemExit("FAIL: second apply duplicated the step")
    if len([item for item in again["sources"] if item["id"] == "prac-20261017-vista8-magpie"]) != 1:
        raise SystemExit("FAIL: second apply duplicated the source")

    if "auto_brief" in json.dumps(pool_suggestions):
        raise SystemExit("FAIL: suggestion carried an auto_brief row")

    import tempfile

    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "schemas" / "candidate.schema.json").read_text(encoding="utf-8"))
    sub = schema["properties"]["atlas_suggestion"]
    validator = Draft202012Validator(sub)
    for item in pool_suggestions:
        body = {key: value for key, value in item.items() if key != "id"}
        errors = sorted(validator.iter_errors(body), key=lambda err: list(err.path))
        if errors:
            raise SystemExit(f"FAIL: atlas_suggestion schema {errors[0].message}")

    with tempfile.TemporaryDirectory() as tmp:
        pool = Path(tmp) / "pool"
        (pool / "candidates").mkdir(parents=True)
        day = pool / "candidates" / "2026-10-21.jsonl"
        day.write_text(
            "".join(dumps_record(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        out = write_pool_suggestions(pool, pool_suggestions)
        text = out.read_text(encoding="utf-8")
        if sentinel in text:
            raise SystemExit("FAIL: pool suggestion file copied snippet")
        kept = [json.loads(line) for line in day.read_text(encoding="utf-8").splitlines()]
        suggested = {row["id"]: row for row in kept if "atlas_suggestion" in row}
        if set(suggested) != set(by_pool):
            raise SystemExit(f"FAIL: candidate suggestions {set(suggested)}")
        dropped = next(row for row in kept if row["id"] == "cand-20261021-ddddeeeeffff")
        if "atlas_suggestion" in dropped:
            raise SystemExit("FAIL: dropped row kept a topic suggestion")
        public_out = PUBLIC / "_suggest_should_not_write.jsonl"
        try:
            assert_not_public(public_out)
            write_ok = True
        except IngestError:
            write_ok = False
        if write_ok:
            raise SystemExit("FAIL: pool suggestion path under public/ was accepted")

    cfg = (ROOT / "config.json").read_text(encoding="utf-8")
    if '"practice_handles"' not in cfg:
        raise SystemExit("FAIL: config missing")
    print("OK suggest_atlas_topics self-check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suggest atlas topics for the practice lane.")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--atlas", type=Path, default=PUBLIC / "data" / "atlas.source.json")
    parser.add_argument("--public", type=Path, default=PUBLIC)
    parser.add_argument(
        "--suggestions",
        type=Path,
        default=PUBLIC / "data" / "topic-suggestions.json",
    )
    parser.add_argument("--pool-dir", type=Path, default=None)
    parser.add_argument("--apply", type=Path, default=None, help="Human confirm file. Refuses unverified cards.")
    parser.add_argument("--derive", action="store_true", help="After a successful apply, run generate_derived.py")
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if args.apply and args.pool_dir:
        raise SystemExit("FAIL: --apply 写公开图谱；--pool-dir 只写私有建议。分开跑。")
    atlas = _load_atlas(args.atlas)
    cards = load_practice_cards(args.public)
    if args.apply:
        try:
            confirm = json.loads(args.apply.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FAIL: 确认文件不是 JSON: {exc}")
        items = confirm.get("items") if isinstance(confirm, dict) else None
        if not isinstance(items, list) or not items:
            raise SystemExit("FAIL: 确认文件要有非空 items")
        try:
            updated = apply_confirmations(atlas, cards, items)
        except ApplyError as exc:
            raise SystemExit(f"FAIL: {exc}")
        _dump(args.atlas, updated)
        print(f"atlas: 已按确认写入 {args.atlas}（{len(items)} 条）。未改 practice.json 的 verified。")
        if args.derive:
            from generate_derived import main as derive_main

            derive_main()
        else:
            print("下一步: python3 scripts/generate_derived.py")
        return 0

    generated_at = args.now or utc_now_iso()
    document = public_document(suggest_public(atlas, cards), generated_at)
    for item in document["items"]:
        if not str(item["id"]).startswith("prac-"):
            raise SystemExit("FAIL: 公开建议只收录 prac- 卡片")
    _dump(args.suggestions, document)
    print(f"suggestions: {len(document['items'])} public practice cards → {args.suggestions}")
    if args.pool_dir:
        handles = _handles()
        pairs = read_pool(args.pool_dir)
        pool_rows = [row for _path, row in pairs]
        suggestions = suggest_pool(atlas, pool_rows, handles, cards)
        out = write_pool_suggestions(args.pool_dir, suggestions)
        print(f"pool suggestions: {len(suggestions)} → {out}（未写公开手册）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IngestError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
