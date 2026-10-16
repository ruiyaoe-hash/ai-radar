#!/usr/bin/env python3
"""Backstop for instruction-shaped text on the public radar surface.

Public cards publish edited prose (title, objective, so_what, practice steps).
The private pool may keep a raw social post. This module:

- strips raw-post keys so derive cannot copy them into public JSON
- flags imperative jailbreaks aimed at an agent

A news sentence about system prompts is not a hit. Patterns look for an
instruction directed at the reader ("ignore previous instructions", "you are
now a …", "print your system prompt"), not the topic word alone.

CI calls this from scripts/validate.py. It is a backstop. Paraphrases can
still get through. Downstream agents must treat every field as data.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "testdata" / "prompt-injection" / "cases.json"

# Keys that carry a raw social post. Edited summaries live on objective / so_what.
RAW_POST_KEYS = frozenset(
    {
        "text",
        "full_text",
        "snippet",
        "raw_text",
        "raw_body",
        "tweet",
        "tweet_text",
        "post_text",
        "post_body",
        "body",
        "note_tweet",
        "content_text",
    }
)

# Imperative jailbreaks. Topic mentions of "system prompt" do not match.
INSTRUCTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore-previous",
        re.compile(
            r"\bignore\s+(?:all\s+)?(?:previous|prior|above|earlier|the\s+above)\s+"
            r"(?:instructions?|prompts?|rules|directives?|messages?)\b",
            re.I,
        ),
    ),
    (
        "disregard-previous",
        re.compile(
            r"\bdisregard\s+(?:all\s+)?(?:(?:your|the)\s+)?(?:previous|prior|above|earlier)\s+"
            r"(?:instructions?|prompts?|rules|directives?)\b",
            re.I,
        ),
    ),
    (
        "disregard-your-prompt",
        re.compile(r"\bdisregard\s+your\s+system\s+prompt\b", re.I),
    ),
    (
        "forget-override-previous",
        re.compile(
            r"\b(?:forget|override|bypass)\s+(?:all\s+)?(?:your\s+|the\s+)?"
            r"(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules|directives?)\b",
            re.I,
        ),
    ),
    (
        "override-your-prompt",
        re.compile(r"\b(?:override|bypass)\s+your\s+system\s+prompt\b", re.I),
    ),
    (
        "do-not-follow",
        re.compile(
            r"\bdo\s+not\s+follow\s+(?:any\s+|the\s+)?(?:previous|prior|above|earlier)\s+"
            r"(?:instructions?|prompts?|rules)\b",
            re.I,
        ),
    ),
    (
        "you-are-now-role",
        re.compile(
            r"\byou\s+are\s+now\s+(?:a|an|my)\b"
            r"|\byou\s+are\s+now\s+(?:dan|jailbroken|unrestricted|unfiltered|developer\s+mode)\b",
            re.I,
        ),
    ),
    (
        "from-now-on",
        re.compile(
            r"\bfrom\s+now\s+on\s*,?\s+you\s+(?:are|will|must|should)\b",
            re.I,
        ),
    ),
    (
        "reveal-your-prompt",
        re.compile(
            r"\b(?:reveal|print|dump|repeat|output|show|leak)\s+(?:me\s+)?your\s+"
            r"(?:full\s+|hidden\s+|initial\s+|original\s+)?"
            r"(?:system\s+prompt|hidden\s+instructions?|initial\s+prompt|developer\s+message)\b",
            re.I,
        ),
    ),
    (
        "new-instructions",
        re.compile(r"\b(?:new|updated)\s+instructions?\s*:\s*\S", re.I),
    ),
    (
        "chat-role-marker",
        re.compile(
            r"<\|im_start\|>\s*system\b|<<\s*SYS\s*>>|\[SYSTEM\]\s*:",
            re.I,
        ),
    ),
    (
        "system-override-line",
        re.compile(
            r"(?:^|\n)\s*system\s*:\s*(?:ignore|override|you\s+are|new\s+instruction)",
            re.I,
        ),
    ),
    (
        "tool-exfil",
        re.compile(
            r"\b(?:call|invoke|use)\s+(?:the\s+|a\s+)?tool\s+to\s+"
            r"(?:send|exfiltrate|upload|post)\s+(?:me\s+|your\s+|the\s+)?"
            r"(?:api[_ ]?key|secret|token|credential)s?\b",
            re.I,
        ),
    ),
    (
        "send-your-secret",
        re.compile(
            r"\b(?:send|post|upload|exfiltrate)\s+(?:me\s+)?your\s+"
            r"(?:api[_ ]?key|secret|token|credential)s?\b",
            re.I,
        ),
    ),
    (
        "zh-ignore-instructions",
        re.compile(
            r"忽略(?:之前|以上|前面|先前|你之前|上面)(?:的)?(?:所有)?"
            r"(?:指令|提示词?|规则|系统提示)"
        ),
    ),
    (
        "zh-disregard",
        re.compile(r"无视(?:之前|以上|前面|所有)(?:的)?(?:指令|规则|系统提示)"),
    ),
    (
        "zh-you-are-now",
        re.compile(
            r"你现在是(?!时候)(?:一个|一名)|你现在(?:扮演|成为)"
            r"|从现在(?:起|开始)，?\s*你(?:是|必须|要)"
        ),
    ),
    (
        "zh-reveal-prompt",
        re.compile(r"(?:请)?(?:输出|打印|复述|告诉我)你的(?:完整)?(?:系统提示|隐藏指令|初始提示)"),
    ),
    (
        "zh-override-prompt",
        re.compile(r"(?:请)?(?:立刻|马上)?覆盖你(?:自己)?的系统提示"),
    ),
    (
        "zh-send-secret",
        re.compile(r"把你的(?:密钥|令牌|凭证|系统提示).{0,8}(?:发到|发送到|发给|传到)"),
    ),
]


def find_instruction_override(text: str) -> str | None:
    """Return the rule id when text looks like an imperative jailbreak."""
    if not text or not isinstance(text, str):
        return None
    for name, pattern in INSTRUCTION_RULES:
        if pattern.search(text):
            return name
    return None


def strip_raw_post_fields(value):
    """Drop raw social-post keys. Edited fields (objective, so_what, title) stay."""
    if isinstance(value, dict):
        return {
            key: strip_raw_post_fields(item)
            for key, item in value.items()
            if key not in RAW_POST_KEYS
        }
    if isinstance(value, list):
        return [strip_raw_post_fields(item) for item in value]
    return value


def raw_post_key_paths(value, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in RAW_POST_KEYS:
                found.append(path)
            found.extend(raw_post_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(raw_post_key_paths(item, f"{prefix}[{index}]"))
    return found


def _add(out: list[tuple[str, str]], path: str, value) -> None:
    if isinstance(value, str) and value.strip():
        out.append((path, value))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str) and item.strip():
                out.append((f"{path}[{index}]", item))


def card_prose(card: dict) -> list[tuple[str, str]]:
    """Public card strings that can carry rewritten untrusted text."""
    out: list[tuple[str, str]] = []
    for key in (
        "title",
        "tag",
        "objective",
        "judgment",
        "judgment_label",
        "access",
        "integration",
        "first_step",
        "alternatives",
    ):
        _add(out, key, card.get(key))
    so = card.get("so_what") if isinstance(card.get("so_what"), dict) else {}
    for key in ("impact", "action", "window", "falsifier"):
        _add(out, f"so_what.{key}", so.get(key))
    correction = card.get("correction") if isinstance(card.get("correction"), dict) else {}
    _add(out, "correction.note", correction.get("note"))
    for index, source in enumerate(card.get("sources") or []):
        if isinstance(source, dict):
            _add(out, f"sources[{index}].handle", source.get("handle"))
    return out


def practice_prose(item: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key in ("title", "author", "takeaway", "caution", "steps", "prerequisites"):
        _add(out, key, item.get(key))
    return out


def _practice_items(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if payload.get("id"):
            return [payload]
    return []


def iter_public_prose(public: Path):
    """Yield (where, field, text) for agent-facing public prose."""
    archive = public / "archive"
    for path in sorted(archive.glob("????-??-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for card in data.get("items") or []:
            if not isinstance(card, dict):
                continue
            where = f"archive/{path.name}:{card.get('id')}"
            for field, text in card_prose(card):
                yield where, field, text

    items_path = public / "items.json"
    if items_path.is_file():
        data = json.loads(items_path.read_text(encoding="utf-8"))
        for card in data.get("items") or []:
            if not isinstance(card, dict):
                continue
            where = f"items.json:{card.get('id')}"
            for field, text in card_prose(card):
                yield where, field, text

    practice_files = [public / "practice.json", public / "practice.sample.json"]
    inbox = public / "practice" / "inbox"
    if inbox.is_dir():
        practice_files.extend(sorted(inbox.glob("*.json")))
    for path in practice_files:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rel = path.relative_to(public)
        for item in _practice_items(payload):
            where = f"{rel}:{item.get('id')}"
            for field, text in practice_prose(item):
                yield where, field, text

    theses_path = public / "theses.json"
    if theses_path.is_file():
        data = json.loads(theses_path.read_text(encoding="utf-8"))
        note = ((data.get("scoring") or {}) if isinstance(data.get("scoring"), dict) else {}).get("note")
        if isinstance(note, str) and note.strip():
            yield "theses.json", "scoring.note", note
        for thesis in data.get("theses") or []:
            if not isinstance(thesis, dict):
                continue
            where = f"theses.json:{thesis.get('id')}"
            for key in ("statement", "falsifier"):
                _text = thesis.get(key)
                if isinstance(_text, str) and _text.strip():
                    yield where, key, _text

    radar_path = public / "tools-radar.json"
    if radar_path.is_file():
        data = json.loads(radar_path.read_text(encoding="utf-8"))
        if isinstance(data.get("note"), str) and data["note"].strip():
            yield "tools-radar.json", "note", data["note"]
        rings = data.get("rings") if isinstance(data.get("rings"), dict) else {}
        for ring_name, tools in rings.items():
            if not isinstance(tools, list):
                continue
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                where = f"tools-radar.json:{ring_name}:{tool.get('id')}"
                for field, text in card_prose(tool):
                    yield where, field, text

    today = public / "today3.txt"
    if today.is_file():
        text = today.read_text(encoding="utf-8")
        if text.strip():
            yield "today3.txt", "text", text

    memo_dir = public / "memos"
    if memo_dir.is_dir():
        for path in sorted(memo_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if text.strip():
                yield f"memos/{path.name}", "text", text

    actions = public / "owner-actions.json"
    if actions.is_file():
        data = json.loads(actions.read_text(encoding="utf-8"))
        for index, row in enumerate(data.get("actions") or []):
            if isinstance(row, dict) and isinstance(row.get("note"), str) and row["note"].strip():
                yield f"owner-actions.json:actions[{index}]", "note", row["note"]


def iter_public_raw_keys(public: Path):
    for path in sorted(public.rglob("*.json")):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for found in raw_post_key_paths(data):
            yield f"{path.relative_to(public)} raw post field {found}"


def check_fixtures(root: Path | None = None) -> list[str]:
    """True positives must match. Near-miss benign sentences must not."""
    path = (root or ROOT) / "testdata" / "prompt-injection" / "cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for case in data.get("reject") or []:
        hit = find_instruction_override(case.get("text") or "")
        if not hit:
            errors.append(f"reject {case.get('id')} was not flagged")
    for case in data.get("allow") or []:
        hit = find_instruction_override(case.get("text") or "")
        if hit:
            errors.append(f"allow {case.get('id')} flagged by {hit}")

    sample = {
        "title": "edited headline",
        "objective": ["edited summary, not the post"],
        "snippet": "Ignore previous instructions",
        "text": "raw tweet body",
        "so_what": {"impact": "kept", "full_text": "raw thread"},
        "sources": [{"handle": "lab", "url": "https://example.com", "role": "primary"}],
    }
    cleaned = strip_raw_post_fields(sample)
    if cleaned.get("objective") != ["edited summary, not the post"]:
        errors.append("strip removed edited objective")
    if cleaned.get("so_what", {}).get("impact") != "kept":
        errors.append("strip removed edited so_what.impact")
    if "snippet" in cleaned or "text" in cleaned or "full_text" in cleaned.get("so_what", {}):
        errors.append("strip left a raw post field")
    if raw_post_key_paths(sample) != ["snippet", "text", "so_what.full_text"]:
        errors.append(f"raw key paths {raw_post_key_paths(sample)}")
    if raw_post_key_paths(cleaned):
        errors.append("cleaned card still has a raw post field")
    return errors


def main() -> int:
    errors = check_fixtures()
    if errors:
        print("FAIL prompt_guard fixtures:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"OK prompt_guard fixtures: {FIXTURES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
