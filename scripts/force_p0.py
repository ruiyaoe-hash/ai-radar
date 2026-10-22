#!/usr/bin/env python3
"""Forced P0（强制今日必看通道）. Code is the source of truth.

Routines may still double-check. This module does not write the public
archive, 今日必看, or practice inbox. A hit forces the row onto the review
queue (band review / review_p0) and can bypass low-score drops and
edition-date holds. It never promotes.

Three triggers, from the 2026-10-22 misses:

1. frontier_launch — a frontier lab's new agent, product line, or model
   family, including a research preview or a Pro/Max waitlist.
2. runtime_vuln — vendor RCE, unauthenticated takeover, or a mass-runtime
   vuln that names an upgrade version. Non-AI stacks count (visitor hygiene).
3. multi_a_tier — same Shanghai day, same cluster, at least two a_tier
   accounts whose score would already be review. Surface them for an
   explicit promote or skip. Default promote when the text can change this
   week's tool choice; otherwise default skip. The row still stays in the
   queue until a human decides.

  python3 scripts/force_p0.py --self-check
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reprint drops are not independent witnesses. Callers that count evidence
# should import this set instead of inventing a second list.
REPRINT_DROP_REASONS = frozenset({"duplicate_url", "duplicate_event", "no_new_info"})

FRONTIER_HANDLES = frozenset({
    "openai",
    "openai-blog",
    "anthropic",
    "anthropicai",
    "anthropic-news",
    "googledeepmind",
    "deepmind",
    "deepmind-blog",
    "aiatmeta",
    "huggingface",
    "deepseek_ai",
    "mistralai",
    "alibaba_qwen",
    "qwen",
    "qwen-blog",
    "geminiapp",
    "xai",
})

LAB_RE = re.compile(
    r"\b(?:openai|anthropic|deepmind|deepseek|mistral|qwen|xai|huggingface)\b|"
    r"google\s+deepmind|meta\s+ai|hugging\s*face",
    re.I,
)
PRODUCT_RE = re.compile(
    r"claude\s+duet|"
    r"\bgpt-[0-9](?:\.[0-9]+)?\b|"
    r"\bgemini(?:\s*[0-9]+|\s+(?:ultra|pro|flash))\b|"
    r"\bllama\s*[0-9]+\b|"
    r"\bgrok\s*[0-9]+\b|"
    r"\bopus\s*[0-9]",
    re.I,
)

# Each pattern is a launch signal. Named-product wording is applied only when
# the row already names a product, so a lab's ordinary "announce" does not fire.
LAUNCH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("research_preview", re.compile(r"research\s+preview|研究预览", re.I)),
    (
        "waitlist_pro",
        re.compile(
            r"\bwaitlist\b.{0,48}\b(?:pro|max|team|enterprise)\b|"
            r"\b(?:pro|max|team|enterprise)\b.{0,48}\bwaitlist\b|"
            r"(?:候补|排队|waitlist).{0,32}(?:\bpro\b|\bmax\b)|"
            r"(?:\bpro\b|\bmax\b).{0,32}(?:候补|排队|waitlist)",
            re.I,
        ),
    ),
    ("product_line", re.compile(r"product\s+line|产品线", re.I)),
    ("model_family", re.compile(r"model\s+family|模型家族|模型系列", re.I)),
    (
        "new_agent",
        re.compile(
            r"\bnew\s+agent\b|introducing\s+(?:our\s+)?(?:new\s+)?agent\b|新(?:的)?(?:智能体|代理)",
            re.I,
        ),
    ),
)
NAMED_LAUNCH_RE = re.compile(
    r"\b(?:preview|announce(?:s|d)?|launch(?:es|ed|ing)?|now\s+available|generally\s+available)\b|"
    r"研究预览|正式推出|现已开放",
    re.I,
)

VULN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("php2shell", re.compile(r"php2shell", re.I)),
    ("rce", re.compile(r"\brce\b|remote\s+code\s+execution|远程(?:代码)?执行", re.I)),
    (
        "unauth_takeover",
        re.compile(
            r"unauth(?:enticated|orized)?\s+(?:takeover|rce|access)|"
            r"未授权(?:接管|访问|远程)|pre-?auth\s+(?:rce|takeover)",
            re.I,
        ),
    ),
    ("mass_runtime", re.compile(r"mass[- ]runtime", re.I)),
    ("cve", re.compile(r"\bCVE-\d{4}-\d{4,7}\b")),
)
UPGRADE_RE = re.compile(
    r"(?:upgrade|update|patch(?:ed)?|fixed)\s+(?:to|in)\s+v?([0-9]+\.[0-9]+(?:\.[0-9]+){0,2})|"
    r"(?:升级|更新|升)到\s*v?([0-9]+\.[0-9]+(?:\.[0-9]+){0,2})",
    re.I,
)
TOOL_CHOICE_RE = re.compile(
    r"工具选型|换成|改用|可以上手|"
    r"\b(?:switch to|try this|new tool|you can now)\b",
    re.I,
)
TUTORIAL_RE = re.compile(
    r"步骤|howto|\bhow to\b|pip install|npm install|docker compose",
    re.I,
)


def row_text(row: dict) -> str:
    """Title, snippet, and URL only. Notes are machine traces and must not re-trigger."""
    parts = [row.get("title"), row.get("snippet"), row.get("url"), row.get("url_norm")]
    return "\n".join(part for part in parts if isinstance(part, str))


def _handle(row: dict) -> str:
    handle = (row.get("source") or {}).get("handle")
    if isinstance(handle, str):
        return handle.strip().lower()
    return ""


def frontier_context(row: dict, text: str | None = None) -> bool:
    blob = row_text(row) if text is None else text
    if _handle(row) in FRONTIER_HANDLES:
        return True
    if LAB_RE.search(blob) or PRODUCT_RE.search(blob):
        return True
    return False


def launch_triggers(text: str, *, named_product: bool) -> list[str]:
    found = [name for name, pattern in LAUNCH_RULES if pattern.search(text)]
    if named_product and NAMED_LAUNCH_RE.search(text) and "named_product_launch" not in found:
        found.append("named_product_launch")
    return found


def vuln_triggers(text: str) -> list[str]:
    found = [name for name, pattern in VULN_RULES if pattern.search(text)]
    if found and UPGRADE_RE.search(text):
        found.append("upgrade_version")
    return found


def p0_record(
    kinds: list[str],
    triggers: list[str],
    default_action: str,
    tool_choice: bool,
    bypassed: list[str] | None = None,
) -> dict:
    return {
        "active": True,
        "kinds": list(dict.fromkeys(kinds)),
        "triggers": list(dict.fromkeys(triggers)),
        "default_action": default_action if default_action in {"promote", "skip"} else "skip",
        "tool_choice": bool(tool_choice),
        "bypassed": list(dict.fromkeys(bypassed or [])),
        "source": "code",
    }


def merge_p0(left: dict | None, right: dict | None) -> dict | None:
    if left is None:
        return right
    if right is None:
        return left
    default = "promote" if "promote" in {left.get("default_action"), right.get("default_action")} else "skip"
    return p0_record(
        list(left.get("kinds") or []) + list(right.get("kinds") or []),
        list(left.get("triggers") or []) + list(right.get("triggers") or []),
        default,
        bool(left.get("tool_choice") or right.get("tool_choice")),
        list(left.get("bypassed") or []) + list(right.get("bypassed") or []),
    )


def match_row_p0(row: dict) -> dict | None:
    """Kinds 1 and 2. Kind 3 needs the whole cluster and is applied in score_pool."""
    text = row_text(row)
    if not text.strip():
        return None
    kinds: list[str] = []
    triggers: list[str] = []
    named = PRODUCT_RE.search(text) is not None
    launch = launch_triggers(text, named_product=named)
    if launch and (frontier_context(row, text) or named):
        kinds.append("frontier_launch")
        triggers.extend(launch)
    vuln = vuln_triggers(text)
    if "upgrade_version" in vuln and any(item != "upgrade_version" for item in vuln):
        kinds.append("runtime_vuln")
        triggers.extend(vuln)
    if not kinds:
        return None
    tool = bool(TOOL_CHOICE_RE.search(text) or "runtime_vuln" in kinds or "frontier_launch" in kinds)
    # Kinds 1 and 2 are the must-see misses. Default action is promote; a human
    # still has to write the archive. Kind 3 may default to skip.
    return p0_record(kinds, triggers, "promote", tool, [])


def match_multi_a_tier(
    rows: list[dict],
    would_be: dict[str, tuple[str, str]],
    a_tier: set[str],
    day_of,
) -> dict[str, dict]:
    """Same-day a_tier pairs whose v1 band would be review, before P0 overrides it.

    day_of(row) -> Shanghai YYYY-MM-DD or None. Rows that would drop, auto-publish,
    or are reprint drops are not witnesses.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row.get("prefilter") != "PASS":
            continue
        if row.get("status_in_pool") == "dropped" and row.get("drop_reason") in REPRINT_DROP_REASONS:
            continue
        band, _reason = would_be.get(str(row.get("id")), ("", ""))
        if band != "review":
            continue
        handle = _handle(row)
        if handle not in a_tier and row.get("tier_prior") != "a_tier":
            continue
        day = day_of(row)
        cluster = row.get("cluster_id")
        if not day or not isinstance(cluster, str) or not cluster:
            continue
        groups.setdefault((cluster, day), []).append(row)

    found: dict[str, dict] = {}
    for members in groups.values():
        handles = {_handle(row) for row in members if _handle(row)}
        if len(handles) < 2:
            continue
        blobs = [row_text(row) for row in members]
        tool = any(TOOL_CHOICE_RE.search(blob) for blob in blobs)
        record = p0_record(
            ["multi_a_tier"],
            ["multi_a_tier"] + (["tool_choice"] if tool else []),
            "promote" if tool else "skip",
            tool,
            [],
        )
        for row in members:
            rid = str(row.get("id"))
            found[rid] = record
    return found


def assign_p0(row: dict, hit: dict, bypassed: list[str] | None = None) -> dict:
    record = p0_record(
        list(hit.get("kinds") or []),
        list(hit.get("triggers") or []),
        str(hit.get("default_action") or "skip"),
        bool(hit.get("tool_choice")),
        list(hit.get("bypassed") or []) + list(bypassed or []),
    )
    row["force_p0"] = record
    bit = "gate: force_p0 " + ",".join(record["kinds"])
    notes = str(row.get("notes") or "")
    if bit not in notes:
        notes = (notes + " " + bit).strip()
    if record["bypassed"]:
        bypass = "gate: bypassed " + ",".join(record["bypassed"])
        if bypass not in notes:
            notes = (notes + " " + bypass).strip()
    row["notes"] = notes
    return record


def content_flags(row: dict) -> dict:
    """Cheap type hints for v2 freshness. Not a P0 decision by themselves."""
    text = row_text(row)
    role = (row.get("source") or {}).get("role_guess")
    vuln = [name for name, pattern in VULN_RULES if pattern.search(text)]
    named = PRODUCT_RE.search(text) is not None
    launch = launch_triggers(text, named_product=named)
    if vuln and ("runtime_vuln" in ((row.get("force_p0") or {}).get("kinds") or []) or UPGRADE_RE.search(text)):
        content_type = "vuln"
    elif launch or "frontier_launch" in ((row.get("force_p0") or {}).get("kinds") or []):
        content_type = "product_launch"
    elif TUTORIAL_RE.search(text):
        content_type = "tutorial"
    elif role == "analysis":
        content_type = "analysis"
    else:
        content_type = "default"
    return {
        "content_type": content_type,
        "tool_choice": bool(TOOL_CHOICE_RE.search(text)),
        "tutorial": bool(TUTORIAL_RE.search(text)),
    }


def hook_document(rows: list[dict], day: str) -> dict:
    """Review-notify payload. No post body. Not an archive write."""
    items = []
    for row in rows:
        spec = row.get("force_p0") or {}
        if not spec.get("active"):
            continue
        if row.get("status_in_pool") == "dropped":
            continue
        items.append(
            {
                "id": row.get("id"),
                "url": row.get("url_norm") or row.get("url") or "",
                "handle": _handle(row),
                "kinds": list(spec.get("kinds") or []),
                "triggers": list(spec.get("triggers") or []),
                "default_action": spec.get("default_action") or "skip",
                "tool_choice": bool(spec.get("tool_choice")),
                "bypassed": list(spec.get("bypassed") or []),
            }
        )
    items.sort(key=lambda item: (0 if item["default_action"] == "promote" else 1, str(item["id"])))
    return {
        "schema": "ai-radar.pool-p0-hook",
        "version": 1,
        "date": day,
        "source": "code",
        "note": (
            "池内强制 P0 审核钩子。代码是准绳，例程可以再看一眼。"
            "这里不写公开归档，不写今日必看，也不发快讯。"
            "飞书正式 P0 仍只推已经由人写进归档的卡片。"
        ),
        "items": items,
    }


def render_hook_lines(document: dict) -> list[str]:
    """Plain lines a human or feishu_notify can forward. Does not POST."""
    lines = []
    for item in document.get("items") or []:
        lines.append(
            "【AI Radar 池内强制 P0 · 待人审】{kinds}\n"
            "建议={action} 工具选择={tool}\n"
            "{url}\n"
            "id={cid} handle={handle}\n"
            "不写公开归档。要上今日必看仍走人工 PR。".format(
                kinds=",".join(item.get("kinds") or []),
                action=item.get("default_action"),
                tool="yes" if item.get("tool_choice") else "no",
                url=item.get("url") or "",
                cid=item.get("id"),
                handle=item.get("handle") or "",
            )
        )
    return lines


def _load_cases() -> dict:
    path = ROOT / "testdata" / "p0" / "cases.json"
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def self_check() -> None:
    """Known-miss fixtures plus negatives. No network and no pool."""
    payload = _load_cases()
    by_name = {case["name"]: case for case in payload["cases"]}

    duet = by_name["claude-duet-research-preview"]["row"]
    hit = match_row_p0(duet)
    if not hit or "frontier_launch" not in hit["kinds"] or "research_preview" not in hit["triggers"]:
        raise SystemExit(f"FAIL: Claude Duet research preview must be frontier_launch, got {hit}")
    if hit["default_action"] != "promote":
        raise SystemExit("FAIL: frontier launch default action must be promote")

    vuln = by_name["php2shell-upgrade"]["row"]
    vhit = match_row_p0(vuln)
    if not vhit or "runtime_vuln" not in vhit["kinds"] or "upgrade_version" not in vhit["triggers"]:
        raise SystemExit(f"FAIL: PHP2Shell with an upgrade version must be runtime_vuln, got {vhit}")
    if "php2shell" not in vhit["triggers"]:
        raise SystemExit(f"FAIL: PHP2Shell trigger missing: {vhit}")

    bare = dict(vuln)
    bare["snippet"] = "FIXTURE PHP2Shell might be bad, no version named."
    bare["title"] = "FIXTURE PHP2Shell rumor"
    if match_row_p0(bare) is not None:
        raise SystemExit("FAIL: a vuln without an upgrade version must not force P0")

    ordinary = {
        "title": "FIXTURE model weights are up",
        "snippet": "FIXTURE a model release note.",
        "url": "https://openai.com/blog/fixture-score-primary",
        "source": {"channel": "rss", "handle": "openai-blog", "role_guess": "primary"},
    }
    if match_row_p0(ordinary) is not None:
        raise SystemExit("FAIL: an ordinary lab release note must not force P0")

    agents = {
        "title": None,
        "snippet": "FIXTURE agents model release for the same Shanghai day",
        "url": "https://openai.com/blog/fixture-pass",
        "source": {"channel": "rss", "handle": "openai-blog", "role_guess": "primary"},
    }
    if match_row_p0(agents) is not None:
        raise SystemExit("FAIL: gate fixture wording must not force P0")

    chinese = {
        "title": "FIXTURE Claude Duet 研究预览",
        "snippet": "FIXTURE Pro 候补可以排队。",
        "url": "https://example.com/fixture-duet-zh",
        "source": {"channel": "web", "handle": "someone", "role_guess": "report"},
    }
    zhit = match_row_p0(chinese)
    if not zhit or "frontier_launch" not in zhit["kinds"]:
        raise SystemExit(f"FAIL: Chinese 研究预览 wording must match, got {zhit}")

    preview = render_hook_lines(
        hook_document(
            [{"id": "cand-20261022-aaaaaaaaaaa1", "url": "https://example.com/a", "force_p0": hit, "status_in_pool": "active", "source": {"handle": "x"}}],
            "2026-10-22",
        )
    )
    if not preview or "snippet" in preview[0] or "待人审" not in preview[0]:
        raise SystemExit(f"FAIL: hook line leaked a body or missed the review marker: {preview}")
    print("OK force_p0 self-check")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Forced P0 matcher. Rules only; no network.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    parser.error("pass --self-check")
    return 2


if __name__ == "__main__":
    sys.exit(main())
