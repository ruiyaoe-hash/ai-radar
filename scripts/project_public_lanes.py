#!/usr/bin/env python3
"""Place finished public cards for 实战手册 and 专题观察.

Shifts call this after scoring. A practice-lane row that clears both gates
already in the repo becomes one practice card under public/practice/inbox/.
That card is the only public copy: the same event is not also a pick or a brief.
generate_derived.py removes a brief that later matches one of these cards.

  - can-follow-along: at least two finished Chinese steps. Numbered lines and
    sequence words (首先 / 然后 / 接着 / 最后) still count. Continuous Chinese
    instruction prose counts too, once it splits into at least two concrete
    actions. Short replies, opinion, ads, and fluff do not.
  - bookmarks may sort a batch. They never reject a row by themselves.

generate_derived.py then merges that inbox into practice.json. The same run
writes a watch item for a long-horizon analysis that is not a practice row,
not a news brief, and not a pick. Verified stays false. Re-running does not
duplicate an inbox file or a watch id.

An X post often has an empty title and a usable body. The first usable
sentence becomes a provisional title before the Chinese editorial layer, so
a qualifying row is not dropped only because title is blank. A casual
status line (跟大家同步, 没想到搞好了, 不少朋友感兴趣) is not a visitor
title: when the steps are still usable, the card takes a how-to line from
those steps instead of publishing the status line or dropping the row.
English step lists still do not publish. A title can use the Chinese
fallback in editorial_zh. Nothing here writes briefs.

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
# count at a sentence boundary, so ordinary prose is not sliced on 然后 alone.
# Prose how-tos take a second path: split into concrete actions instead.
_STEP_BOUNDARY = re.compile(
    rf"(?:^|[\n；;。])\s*(?:{_STEP_NUM}|{_STEP_WORD})\s*[:：]?"
    rf"|(?<=\s)(?:{_STEP_NUM}|第[0-9一二三四五六七八九十]+步)\s*[:：]?"
)
_SENTENCE_SPLIT = re.compile(r"[。！？!?\n；;]+")
_LEAD_MARK = re.compile(
    rf"^\s*(?:{_STEP_NUM}|{_STEP_WORD})\s*[:：]?\s*"
)
_URL = re.compile(r"https?://\S+")
_CLAUSE_SPLIT = re.compile(r"[。！？!?\n；;，,、]+")
_LEAD_NOISE = re.compile(
    r"^(?:我觉得|我认为|我感觉|个人觉得|说实话|其实|简单来说|做法很简单)[，,\s：:]*"
)
_FLUFF = re.compile(
    r"太强了|绝了|真香|值得关注|值得收藏|值得看看|推荐关注|建议关注|"
    r"个人观点|仅供参考|涨知识|马克一下|可以关注一下"
)
_AD = re.compile(r"扫码|加微信|加v信|私信我|限时优惠|优惠券|折扣码|领取资料|进群领取|广告合作")
# Verbs that are also ordinary nouns do not count when they start those nouns
# (配置文件, 安装门槛, 设置项). The reader has to be told to do something.
_PROCEDURAL_VERB = re.compile(
    r"打开|关掉|关闭|卸载|执行|输入|粘贴|复制|下载|上传|"
    r"填写|填上|填入|登录|登入|注册|创建|新建|删除|修改|替换|"
    r"保存|提交|重启|连接|导入|导出|选择|点击|勾选|添加|写入|"
    r"调用|进入|切换|更新|升级|检查|确认|克隆|拉取|推送|编译|构建|"
    r"验证|启用|禁用|改成|换成|写成|写好|写上|写进|建好|配好|装上|"
    r"跑通|绑定|绑在|接上|接入|指向|指到|贴进|贴上|贴到|"
    r"发给|发出|发一把|拉起|补上|补进|放进|放到|丢进|丢给|整理成|保存成|刷新|加上|发送|"
    r"装(?!饰|修|置|备|满|作|样子|忙)|"
    r"安装(?!量|包|说明|文档|门槛|成本|方式|方法|步骤)|"
    r"运行(?!时|中|结果|日志)|"
    r"配置(?!文件|项|说明|文档|界面|方式)|"
    r"设置(?!项|页|里|界面)|"
    r"生成(?!式|物|结果)|"
    r"部署(?!文档|说明|方式)|"
    r"测试(?!结果|报告)|"
    r"启动(?!项|参数|日志)"
)
_BA_ACTION = re.compile(
    r"把[^，。；\n]{1,24}"
    r"(?:改成|换成|填上|填入|设成|设为|写成|写进|放进|放到|装上|删除|指向|指到|接到|发给|贴进|贴上|保存)"
)
_OBJECT = re.compile(
    r"目录|文件夹|文件|配置|命令行|命令|账号|账户|端口|密钥|钥匙|"
    r"页面|网页|终端|服务器|仓库|依赖|镜像|容器|服务|模型|接口|"
    r"地址|环境变量|脚本|项目|编辑器|浏览器|插件|按钮|菜单|文档|"
    r"代码|分支|隧道|网关|供应商|提示词|输入框|数据库|表格|字段|"
    r"参数|证书|域名|面板|控制台|工作流|模板|请求|日志|进程|"
    r"权限|令牌|用户|属主|客户端|设备|笔记|提纲|文字稿|流程|编排"
)
_COMMAND = re.compile(
    r"(?<![A-Za-z])(?:pip3?|npm|pnpm|yarn|docker|git|curl|wget|uv|mkdir|ssh|brew|sudo)\s+\S",
    re.I,
)
_PRODUCT_OP = re.compile(
    r"(?:打开|安装|运行|登录|进入|部署|启动|调用|装)\s*[A-Za-z][A-Za-z0-9_./:-]{2,}"
)
# Follower status talk. A how-to title names the outcome, not the author's mood.
_STATUS_TALK = re.compile(
    r"没想到|挺顺利|搞好了|搞定了|"
    r"跟大家|同步一下|同步下|汇报一下|更新一下|分享一下|通知一下|"
    r"不少朋友|朋友们感兴趣|"
    r"写个极简|写个教程|写了个教程|写了一版"
)
# Shopping chatter is not the outcome a visitor came for.
_ASIDE = re.compile(r"京东|淘宝|拼多多|到家买|一小时送到|好像\s*\d+\s*多?块")


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


def _step_text(row: dict) -> str:
    """How-to text is the body. A headline is not an extra step.

    X posts usually leave the title empty and put the instructions in the
    snippet. When both exist, counting the headline as a step would turn a
    one-line reply under a how-to title into two actions.
    """
    snippet = row.get("snippet") if isinstance(row.get("snippet"), str) else ""
    if snippet.strip():
        return snippet
    title = row.get("title") if isinstance(row.get("title"), str) else ""
    return title


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


def _norm_step(text: str) -> str:
    return re.sub(r"[\s，,。；;、：:]+", "", text or "")


def _same_step(left: str, right: str) -> bool:
    a, b = _norm_step(left), _norm_step(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return abs(len(a) - len(b)) <= 4
    return False


def _executable_clause(text: str) -> bool:
    """A concrete operation on a tool, file, config, or machine.

    Opinion, ads, and metaphorical 打开/把 do not qualify. A shell command
    counts on its own. A procedural verb still needs an object the reader
    can point at (目录, 账号, 端口, …).
    """
    raw = text or ""
    if _AD.search(raw) or _FLUFF.search(raw):
        return False
    has_command = bool(_COMMAND.search(raw))
    has_verb = bool(_PROCEDURAL_VERB.search(raw) or _BA_ACTION.search(raw) or _PRODUCT_OP.search(raw))
    has_object = bool(_OBJECT.search(raw) or has_command or _PRODUCT_OP.search(raw))
    if has_command and has_object:
        return True
    return has_verb and has_object


_STEP_LEAD = re.compile(
    r"^(?:并且|而且|同时|另外|此外|随后|然后|接着|之后|我已经|已经|刚刚|刚|并|再(?!次)|也(?!许))"
)


def _finish_step(text: str) -> str | None:
    cleaned = _LEAD_MARK.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,;；:：。 \t")
    cleaned = re.sub(r"([把将])\s+", r"\1", cleaned)
    while True:
        nxt = _STEP_LEAD.sub("", cleaned, count=1).strip(" ，,;；:：。 \t")
        if not nxt or nxt == cleaned:
            break
        cleaned = nxt
    if len(cleaned) > 300:
        cut = cleaned[:300]
        if "，" in cut:
            cut = cut.rsplit("，", 1)[0]
        cleaned = cut.strip(" ，,;；")
    if not cleaned or find_instruction_override(cleaned):
        return None
    if not _executable_clause(cleaned) or not visitor_ready(cleaned):
        return None
    return cleaned if cleaned.endswith("。") else cleaned + "。"


def _remember_step(steps: list[str], step: str | None) -> None:
    if not step or any(_same_step(step, prev) for prev in steps):
        return
    steps.append(step)


def _rest_can_step(pieces: list[str]) -> bool:
    buf: list[str] = []
    for piece in pieces:
        if not buf and not _executable_clause(piece):
            continue
        buf.append(piece)
        joined = "，".join(buf)
        if visitor_ready(joined) and _executable_clause(joined):
            return True
    return False


def _clauses(text: str) -> list[str]:
    body = _URL.sub(" ", text or "")
    clauses: list[str] = []
    for part in _CLAUSE_SPLIT.split(body):
        piece = _LEAD_NOISE.sub("", part.strip())
        piece = _LEAD_MARK.sub("", piece)
        piece = re.sub(r"\s+", " ", piece).strip(" ，,;；:：。 \t")
        if not piece or _AD.search(piece) or _FLUFF.search(piece):
            continue
        clauses.append(piece)
    return clauses


def _steps_from_markers(text: str) -> list[str]:
    """Numbered lines and 首先 / 然后 / 接着 / 最后 at a sentence boundary."""
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


def _steps_from_prose(text: str) -> list[str]:
    """Split continuous instructions into steps a visitor can follow.

    Clauses stay together until the buffer is already a finished action and
    the remainder can still make another one. A single sentence, an ad, or
    a pure opinion therefore stays under two steps. The whole post is never
    returned as one step.
    """
    pieces = _clauses(text)
    steps: list[str] = []
    buf: list[str] = []
    full_norm = _norm_step(_URL.sub(" ", text or ""))
    for index, piece in enumerate(pieces):
        if not _executable_clause(piece):
            # Keep a short constraint ("端口只留在本机") glued to the action
            # it qualifies. Commentary with no object stays off the card.
            if buf and _OBJECT.search(piece):
                buf.append(piece)
            continue
        if (
            buf
            and visitor_ready("，".join(buf))
            and _executable_clause("，".join(buf))
            and _rest_can_step(pieces[index:])
        ):
            _remember_step(steps, _finish_step("，".join(buf)))
            buf = []
            if len(steps) >= 8:
                return steps
        buf.append(piece)
    if buf and len(steps) < 8:
        _remember_step(steps, _finish_step("，".join(buf)))
    return [step for step in steps if _norm_step(step) != full_norm][:8]


def extract_steps(text: str) -> list[str]:
    """Can-follow-along gate. A title plus a remark is not a tutorial.

    Numbered or sequenced sentences win when they already yield two finished
    Chinese steps. Otherwise continuous instruction prose is split into
    concrete actions. A short reply, one action, a pure opinion, an ad, or
    non-actionable fluff does not qualify. The public card never receives
    the unparsed post as a single step.
    """
    marked = _steps_from_markers(text)
    if len(marked) >= 2:
        return marked
    prose = _steps_from_prose(text)
    if len(prose) > len(marked):
        return prose
    return marked


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


def casual_status_title(text: str) -> bool:
    """True when the line is the author talking to followers, not a how-to."""
    raw = re.sub(r"\s+", "", text or "")
    if not raw:
        return False
    return bool(_STATUS_TALK.search(raw))


def _outcome_line(steps: list[str]) -> str:
    """A visitor line taken from finished steps.

    Status talk and shopping asides lose to a concrete action. When every
    step is an aside, the first finished step is still returned so a usable
    card is rewritten instead of dropped.
    """
    fallback = ""
    for step in steps:
        candidate = re.sub(r"\s+", " ", step or "").strip().rstrip("。")
        if not candidate or not visitor_ready(candidate) or casual_status_title(candidate):
            continue
        if not fallback:
            fallback = candidate
        if _ASIDE.search(candidate):
            continue
        if _executable_clause(candidate):
            return candidate[:120]
    for step in steps:
        candidate = re.sub(r"\s+", " ", step or "").strip().rstrip("。")
        if (
            candidate
            and visitor_ready(candidate)
            and not casual_status_title(candidate)
            and not _ASIDE.search(candidate)
        ):
            return candidate[:120]
    return fallback[:120]


def _publishable_title(raw_title: str, steps: list[str]) -> str:
    """Keep a finished how-to title. Replace status talk from the steps."""
    title = re.sub(r"\s+", " ", raw_title or "").strip()
    if (
        title
        and visitor_ready(title)
        and not casual_status_title(title)
        and not _ASIDE.search(title)
    ):
        return title[:120]
    fixed = _outcome_line(steps)
    if fixed and visitor_ready(fixed) and not casual_status_title(fixed):
        return fixed[:120]
    if title and visitor_ready(title) and not casual_status_title(title):
        return title[:120]
    return ""


def engagement_weight(row: dict) -> float:
    """Soft rank only. Missing or low favorites do not reject the row."""
    engagement = row.get("engagement")
    if not isinstance(engagement, dict):
        return 0.0
    return _count(engagement.get("bookmarks"))


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
    # bookmark_min stays in the signature so shift callers do not change.
    # It is not a veto. Ordering uses engagement_weight.
    day = _day(row)
    suffix = _suffix(row)
    if not day or not re.fullmatch(r"[a-f0-9]{12}", suffix):
        return None
    steps = extract_steps(_step_text(row))
    if len(steps) < 2:
        return None
    url = row.get("url_norm") or row.get("url") or ""
    if not safe_http_url(url):
        return None
    raw_title = _raw_title(row)
    if not raw_title:
        raw_title = first_usable_sentence(_plain_bits(row)) or ""
    title = _publishable_title(raw_title, steps)
    if not title:
        return None
    summary = _outcome_line(steps) or title
    if casual_status_title(summary) or not visitor_ready(summary):
        summary = title
    edited = edit_pair(title, summary)
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
    if flags.get("tutorial") and len(extract_steps(_step_text(row))) >= 2:
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
            practice.append((engagement_weight(row), card["id"], card))
            continue
        item = project_watch(row, practice_handles, review_min)
        if item and item["id"] not in seen_w:
            seen_w.add(item["id"])
            watch.append(item)
    practice.sort(key=lambda part: (-part[0], part[1]))
    return [part[2] for part in practice], watch


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
    if not card["steps"][0].startswith("安装官方命令行"):
        raise SystemExit(f"FAIL: numbered sequence wording changed {card['steps']}")
    if card["title"] != "用三步把本地模型接到你的编辑器":
        raise SystemExit(f"FAIL: how-to title was rewritten {card['title']}")
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
    for bad in (
        "没想到开发挺顺利，搞好了",
        "跟大家同步下 Kindle 刷机改造进展",
        "不少朋友感兴趣，写个极简版的 Kindle 越狱改造教程",
    ):
        if not casual_status_title(bad):
            raise SystemExit(f"FAIL: status title not detected {bad}")
    for good in (
        "用 Syncthing 给云电脑做单向实时备份",
        "旧 Kindle 越狱后装 KOReader：当微信读书与 Obsidian 阅读器",
        "用三步把本地模型接到你的编辑器",
    ):
        if casual_status_title(good):
            raise SystemExit(f"FAIL: how-to title was treated as status talk {good}")
    status_body = "首先安装官方命令行并登录自己的账号。然后在编辑器里填上本地服务地址。接着用一条真实任务跑通。"
    for index, bad_title in enumerate(
        (
            "没想到开发挺顺利，搞好了",
            "跟大家同步下 Kindle 刷机改造进展",
            "不少朋友感兴趣，写个极简版的 Kindle 越狱改造教程",
        )
    ):
        status_card = project_practice(
            _sample_row(
                id=f"cand-20261025-abc123abc1{index:02x}",
                title=bad_title,
                snippet=status_body,
            ),
            handles,
            0.34,
            floor,
        )
        if not status_card or len(status_card["steps"]) < 2:
            raise SystemExit(f"FAIL: usable steps were dropped for a status title {bad_title} {status_card}")
        if status_card["title"] == bad_title or casual_status_title(status_card["title"]):
            raise SystemExit(f"FAIL: status-line title published {status_card['title']}")
        if not status_card["steps"][0].startswith("安装官方命令行"):
            raise SystemExit(f"FAIL: status-title rewrite changed the steps {status_card['steps']}")
    blank_status = project_practice(
        _sample_row(
            id="cand-20261025-abc123abc140",
            title="",
            snippet="没想到开发挺顺利，搞好了。" + status_body,
        ),
        handles,
        0.34,
        floor,
    )
    if not blank_status or casual_status_title(blank_status["title"]) or "搞好了" in blank_status["title"]:
        raise SystemExit(f"FAIL: empty title published the status sentence {blank_status}")
    shopping = project_practice(
        _sample_row(
            id="cand-20261025-abc123abc141",
            title="没想到开发挺顺利，搞好了",
            snippet=(
                "1. 京东到家买一个绿联的 type-c 转 micro-usb 线，好像20 多块，一小时送到家 "
                "2. 用数据线连上 Kindle，让助手完成越狱 "
                "3. 装上 KOReader 阅读插件并打开一本书"
            ),
        ),
        handles,
        0.34,
        floor,
    )
    if not shopping or len(shopping["steps"]) < 2:
        raise SystemExit(f"FAIL: shopping aside dropped a usable how-to {shopping}")
    if "京东" in shopping["title"] or casual_status_title(shopping["title"]):
        raise SystemExit(f"FAIL: aside or status line became the title {shopping['title']}")
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
    quiet_card = project_practice(quiet, handles, 0.34, floor)
    if not quiet_card or len(quiet_card["steps"]) < 2:
        raise SystemExit("FAIL: a finished how-to was dropped for low favorites")
    unsaved = _sample_row(id="cand-20261024-abc123abc12c")
    unsaved.pop("engagement", None)
    if project_practice(unsaved, handles, 0.34, floor) is None:
        raise SystemExit("FAIL: a finished how-to was dropped because favorites were missing")
    ranked, _unused_watch = project_rows([quiet, _sample_row()], handles, 0.34, floor)
    if [item["id"] for item in ranked][0] != "prac-20261024-abc123abc123":
        raise SystemExit(f"FAIL: bookmarks did not soft-rank { [item['id'] for item in ranked] }")
    short = _sample_row(
        id="cand-20261024-abc123abc12d",
        snippet="1. 点保存 2. 再点一次",
    )
    if project_practice(short, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a thin two-liner became a practice card")
    prose_body = (
        "用一台服务器把私人模型网关跑起来，各台电脑只连同一个地址。"
        "在服务器上建好配置目录，并把属主改成容器使用的用户。"
        "按官方文档写好编排文件，客户端端口和管理端口分开，管理端口只绑在本机。"
        "启动服务之后，从自己的电脑打开隧道，再在管理页里接上模型供应商。"
        "给每台设备单独发一把网关钥匙，客户端只填写网关地址，用一条请求确认模型列表能返回。"
    )
    if len(_steps_from_markers(prose_body)) >= 2:
        raise SystemExit("FAIL: prose fixture was accepted by the numbered gate")
    prose = _sample_row(
        id="cand-20261024-abc123abc131",
        title="",
        snippet=prose_body,
    )
    prose_card = project_practice(prose, handles, 0.34, floor)
    if not prose_card or len(prose_card["steps"]) < 2 or prose_card["verified"] is not False:
        raise SystemExit(f"FAIL: continuous Chinese how-to was dropped {prose_card}")
    if not visitor_ready(prose_card["title"]) or not visitor_ready(prose_card["takeaway"]):
        raise SystemExit(f"FAIL: prose card is not finished Chinese {prose_card}")
    if any(_norm_step(step) == _norm_step(prose_body) or len(step) >= len(prose_body) for step in prose_card["steps"]):
        raise SystemExit(f"FAIL: prose card kept an unparsed wall {prose_card['steps']}")
    if any(re.match(r"^(并|再(?!次)|然后|接着)", step) for step in prose_card["steps"]):
        raise SystemExit(f"FAIL: prose step still starts with a leftover connector {prose_card['steps']}")
    joined = (
        "在服务器上建好配置目录并把属主改成运行用户，"
        "按官方文档写好编排文件并拉起容器，"
        "从自己的电脑打开隧道后再到管理页接上供应商，"
        "给每台设备单独发一把网关钥匙。"
    )
    joined_steps = extract_steps(joined)
    if len(joined_steps) < 2 or any(len(step) >= len(joined) for step in joined_steps):
        raise SystemExit(f"FAIL: one-sentence how-to was not split {joined_steps}")
    bare = _sample_row(
        id="cand-20261024-abc123abc136",
        title="",
        snippet="安装官方命令行并登录自己的账号，在编辑器里填上本地服务地址，用一条真实任务把流程跑通。",
    )
    bare_card = project_practice(bare, handles, 0.34, floor)
    if not bare_card or len(bare_card["steps"]) < 2:
        raise SystemExit(f"FAIL: unnumbered Chinese instructions were dropped {bare_card}")
    opinion = _sample_row(
        id="cand-20261024-abc123abc132",
        snippet="我觉得这个方向以后会很有意思，大家可以关注一下后续进展，真的太强了，值得收藏。",
    )
    if project_practice(opinion, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a pure opinion became a practice card")
    fluff = _sample_row(
        id="cand-20261024-abc123abc135",
        snippet="可以把视野打开一些，也可以把标准放宽一点，以后会很不一样。",
    )
    if project_practice(fluff, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: non-actionable fluff became a practice card")
    ad = _sample_row(
        id="cand-20261024-abc123abc133",
        snippet="限时优惠最后一天，扫码加微信领取全套资料，私信我还能再拿折扣码，名额不多赶紧进群领取。",
    )
    if project_practice(ad, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: an ad became a practice card")
    one_liner = _sample_row(
        id="cand-20261024-abc123abc134",
        snippet="把仓库克隆到本地安装依赖就能跑。",
    )
    if project_practice(one_liner, handles, 0.34, floor) is not None:
        raise SystemExit("FAIL: a one-action line became a practice card")
    prose_quiet = _sample_row(
        id="cand-20261024-abc123abc137",
        title="",
        snippet=prose_body,
        engagement={"likes": 40, "bookmarks": 2, "captured_at": "2026-10-24T02:00:00Z"},
    )
    if project_practice(prose_quiet, handles, 0.34, floor) is None:
        raise SystemExit("FAIL: a finished prose how-to was dropped for low favorites")
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
    if not english_watch or not visitor_ready(english_watch["title"]) or not visitor_ready(english_watch["summary"]):
        raise SystemExit(f"FAIL: English analysis was dropped instead of translated {english_watch}")
    if "成本" not in english_watch["title"] + english_watch["summary"]:
        raise SystemExit(f"FAIL: translated watch did not explain the cost note {english_watch}")
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
