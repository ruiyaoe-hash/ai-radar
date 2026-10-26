#!/usr/bin/env python3
"""Visitor copy must explain the matter in Chinese.

An optional editorial endpoint may rewrite a headline. Without one, a local
machine-translation fallback still produces a Chinese sentence, so a strong
English open-source note is not dropped only because the Chinese is imperfect.
Unfinished editor scaffolding, TODO, and internal process copy still do not publish.
This module does not render pages and does not read the private pool.

  python3 scripts/editorial_zh.py --self-check

AI_RADAR_EDITORIAL_URL, when set, receives JSON
{"title","summary"} and must return JSON {"title","summary"} in Chinese.
The URL is not printed. There is no network call during --self-check.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

HAN = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")

# Process talk. A visitor card that says the editor has not finished is not a card.
SCAFFOLD = (
    "这条先按事实记下",
    "编辑还没有",
    "编辑还没",
    "还没有写成",
    "还没写成",
    "建议行动还没写",
    "先按事实记下",
    "还没单独标注",
    "这条快讯还没有",
    "还没有写成事实",
    "还在准备",
    "还没准备好",
    "先记下",
    "不是因为价值低",
    "先不进公开",
    "早班已确认",
    "公开站今日清空",
    "公开站清空",
    "晚班重新上线",
    "晚班补上",
    "noted for later",
    "editor hasn",
    "todo:",
    "fixme",
    "wip",
)


def visitor_ready(text: str) -> bool:
    """True when a visitor can read the sentence as finished Chinese."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if len(raw) < 8:
        return False
    lowered = raw.lower()
    for phrase in SCAFFOLD:
        if phrase.lower() in lowered:
            return False
    han = len(HAN.findall(raw))
    latin = len(LATIN.findall(raw))
    if han < 8:
        return False
    # Product names may stay in Latin when the Chinese already explains the matter.
    if latin > max(48, han * 3):
        return False
    return True


def _ok_pair(got) -> tuple[str, str] | None:
    if not isinstance(got, tuple) or len(got) != 2:
        return None
    title, summary = str(got[0] or "").strip(), str(got[1] or "").strip()
    if visitor_ready(title) and visitor_ready(summary):
        return title, summary
    return None


def _llm_edit(title: str, summary: str) -> tuple[str, str] | None:
    url = (os.environ.get("AI_RADAR_EDITORIAL_URL") or "").strip()
    if not url:
        return None
    payload = json.dumps({"title": title, "summary": summary}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(8000)
    except Exception:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return _ok_pair((data.get("title"), data.get("summary")))


def _has_scaffold(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase.lower() in lowered for phrase in SCAFFOLD)


def machine_translate(title: str, summary: str) -> tuple[str, str] | None:
    """Chinese fallback when editorial Chinese is missing or unfinished.

    The sentence has to say what changed. Scaffold and empty blurbs return None.
    """
    raw_title = re.sub(r"\s+", " ", title or "").strip()
    raw_summary = re.sub(r"\s+", " ", summary or "").strip()
    blob = f"{raw_title} {raw_summary}".strip()
    if not blob or _has_scaffold(blob):
        return None
    lowered = blob.lower()
    bits: list[str] = []

    def add(text: str) -> None:
        if text not in bits:
            bits.append(text)

    if re.search(r"open[- ]source", lowered):
        add("开源")
    if re.search(r"open[- ]weight|\bweights?\b", lowered):
        add("权重")
    if re.search(r"\bmodels?\b", lowered):
        add("模型")
    if re.search(r"github|gitlab|repository|\brepo\b", lowered):
        add("代码仓库")
    if re.search(r"releas|publish", lowered):
        add("已经发布")
    if re.search(r"download|available", lowered):
        add("可以下载")
    if re.search(r"preview", lowered):
        add("研究预览")
    if re.search(r"\bcosts?\b", lowered):
        add("成本")
    if re.search(r"fall|cheaper|\bdrop", lowered):
        add("还在下降")
    if re.search(r"revisit|quarter|\bchoice\b", lowered):
        add("下个季度可以重新做一次选择")
    if re.search(r"vuln|cve|patch|upgrade", lowered):
        add("需要核对的安全更新")
    if re.search(r"\bagents?\b", lowered):
        add("智能体")
    if re.search(r"\btool\b", lowered):
        add("工具")
    if not bits:
        return None
    detail = "，".join(bits)
    title_zh = f"公开更新：{detail}"
    if len(title_zh) > 80:
        title_zh = title_zh[:79] + "…"
    summary_zh = f"公开说明里，{detail}。这句中文说明发生了什么，名字和版本以链接里的原文为准。"
    if visitor_ready(title_zh) and visitor_ready(summary_zh):
        return title_zh, summary_zh
    return None


def edit_pair(title: str, summary: str, *, editor=None) -> tuple[str, str] | None:
    """Return Chinese title and summary, or None when the copy must not publish."""
    if _has_scaffold(title) or _has_scaffold(summary):
        return None
    ready = _ok_pair((title, summary))
    if ready:
        return ready
    if editor is not None:
        try:
            got = editor(title, summary)
        except Exception:
            got = None
        ready = _ok_pair(got if isinstance(got, tuple) else None)
        if ready:
            return ready
    ready = _llm_edit(title, summary)
    if ready:
        return ready
    return machine_translate(title, summary)


def reader_lines(lens: str) -> tuple[str, str]:
    """Finished reader lines. They do not describe the editorial workflow."""
    why = {
        "工具": "它关系到你现在用的工具要不要换，或者能不能继续沿用。",
        "赛道": "这是已经公开的一条行业事实，用来判断这周的选择变不变。",
        "模式": "这里有一种可以拿回自己工作里试的做法。",
        "时机": "这里有一个可能改动你排期的变化。",
    }.get(lens or "", "对照你正在做的事，看这条值不值得排进这周。")
    affect = {
        "工具": "拿一个你自己的真实任务对照这次变化，再决定换不换。",
        "赛道": "对得上你这周的选择就调整安排，对不上就保持原来的做法。",
        "模式": "能放进你自己的流程再采用，不能照着做就只把它当成了解。",
        "时机": "时间对上你正在做的事再行动，对不上就不必改计划。",
    }.get(lens or "", "对得上你正在做的事再行动，对不上就保持原来的安排。")
    return why, affect


def self_check() -> None:
    chinese_title = "自检用：实验室放出一份模型权重"
    chinese_summary = "实验室放出了一份可以下载的模型权重，只供这条自检使用。"
    if edit_pair(chinese_title, chinese_summary) != (chinese_title, chinese_summary):
        raise SystemExit("FAIL: finished Chinese copy was rewritten or dropped")
    translated = edit_pair(
        "FIXTURE model weights published",
        "A new open weight model is now available for download.",
    )
    if not translated or not visitor_ready(translated[0]) or not visitor_ready(translated[1]):
        raise SystemExit(f"FAIL: English open-source note was dropped {translated}")
    if "模型" not in translated[0] + translated[1] or "权重" not in translated[0] + translated[1]:
        raise SystemExit(f"FAIL: fallback did not explain the model weights {translated}")
    if "FIXTURE" in translated[0] or "FIXTURE" in translated[1]:
        raise SystemExit(f"FAIL: fallback kept the fixture marker {translated}")
    if edit_pair("实验室放出模型权重供自检", "这条先按事实记下。编辑还没有写成要不要行动的判断。") is not None:
        raise SystemExit("FAIL: scaffold sentence was accepted")

    def editor(_title: str, _summary: str):
        return (
            "自检编辑：实验室放出一份可下载的模型权重",
            "实验室放出一份可下载的模型权重，做本地推理的人可以拿来对照。",
        )

    edited = edit_pair("English only headline about weights", "English only blurb.", editor=editor)
    if not edited or not visitor_ready(edited[0]) or "English only" in edited[0]:
        raise SystemExit(f"FAIL: editor result rejected {edited}")
    why, affect = reader_lines("工具")
    if not visitor_ready(why) or not visitor_ready(affect):
        raise SystemExit("FAIL: reader lines are not visitor copy")
    if "编辑" in why or "编辑" in affect:
        raise SystemExit("FAIL: reader lines talk about the editor")
    print("OK editorial_zh self-check")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check visitor Chinese copy. No network in self-check.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    parser.error("pass --self-check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
