#!/usr/bin/env python3
"""Render content/posts/*.md into public/blog/.

Writes:
  - blog/index.html     (post list)
  - blog/<slug>.html    (one static page per post)
  - blog/posts.json     (machine-readable list; the homepage reads it)

Front matter is a block of `key: value` lines between two `---` lines.
Required: title, date (YYYY-MM-DD), summary. Optional: title_en, slug, tags
(comma separated), draft (true skips the post).

The Markdown subset is deliberately small: ## / ### headings, paragraphs,
- / 1. lists, > quotes, ``` fences, --- rules, `code`, **bold**, and
[text](url). Every character of source text is HTML-escaped. Links must be
http(s) or a site-relative path; anything else renders as plain text. Raw HTML
in a post is shown as text, never as markup.

  python3 scripts/build_blog.py              # write public/blog/
  python3 scripts/build_blog.py --self-check # offline renderer checks
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "content" / "posts"
PUBLIC = ROOT / "public"
BLOG_DIR = PUBLIC / "blog"
SITE = "https://ruiyaoe-hash.github.io/ai-radar/"
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://static.cloudflareinsights.com; "
    "script-src-attr 'none'; "
    "style-src 'self'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self' https://cloudflareinsights.com; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-src 'none'"
)
FEEDBACK_FORM = "https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
INLINE_RE = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n]+)\*\*")
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def esc(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def safe_link(url: str) -> tuple[str, bool]:
    """Return (href, external). Empty href means the link is not allowed."""
    raw = url.strip()
    if not raw or any(c.isspace() or ord(c) < 32 or c in '<>"\'`\\' for c in raw):
        return "", False
    if raw.startswith("//"):
        return "", False
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme:
        if parts.scheme.lower() in {"http", "https"} and parts.netloc:
            return raw, True
        return "", False
    if re.match(r"^[a-zA-Z][a-zA-Z+\-.]*:", raw):
        return "", False
    return raw, False


def inline(text: str) -> str:
    out: list[str] = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        code, label, url, bold = m.groups()
        if code is not None:
            out.append(f"<code>{esc(code)}</code>")
        elif bold is not None:
            out.append(f"<strong>{esc(bold)}</strong>")
        else:
            href, external = safe_link(url)
            if not href:
                out.append(esc(label))
            else:
                extra = ' target="_blank" rel="noopener noreferrer"' if external else ""
                out.append(f'<a href="{esc(href)}"{extra}>{esc(label)}</a>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def render_markdown(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    para: list[str] = []
    items: list[str] = []
    list_tag = ""
    quote: list[str] = []
    i = 0

    def flush() -> None:
        nonlocal list_tag
        if para:
            blocks.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            body = "".join(f"<li>{inline(x)}</li>" for x in items)
            blocks.append(f"<{list_tag}>{body}</{list_tag}>")
            items.clear()
            list_tag = ""
        if quote:
            blocks.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
            quote.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(f"<pre><code>{esc(chr(10).join(code))}</code></pre>")
            i += 1
            continue
        if not stripped:
            flush()
        elif stripped == "---":
            flush()
            blocks.append("<hr />")
        elif m := re.match(r"^(#{1,3})\s+(.+)$", stripped):
            flush()
            level = 3 if len(m.group(1)) == 3 else 2
            blocks.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
        elif m := re.match(r"^>\s?(.*)$", stripped):
            if para or items:
                flush()
            quote.append(m.group(1))
        elif m := re.match(r"^(?:[-*]|(\d+)\.)\s+(.+)$", stripped):
            tag = "ol" if m.group(1) else "ul"
            if para or quote or (items and tag != list_tag):
                flush()
            list_tag = tag
            items.append(m.group(2))
        elif items and line.startswith("  "):
            items[-1] += " " + stripped
        else:
            if items or quote:
                flush()
            para.append(stripped)
        i += 1
    flush()
    return "\n".join(blocks)


def parse_post(path: Path) -> dict | None:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise SystemExit(f"{path.name}: missing front matter")
    meta: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SystemExit(f"{path.name}: bad front matter line {line!r}")
        meta[key.strip()] = value.strip()
    if meta.get("draft", "").lower() == "true":
        return None
    file_m = FILE_RE.match(path.name)
    slug = meta.get("slug") or (file_m.group(2) if file_m else path.stem)
    date = meta.get("date") or (file_m.group(1) if file_m else "")
    for field, value in (("title", meta.get("title")), ("summary", meta.get("summary"))):
        if not value:
            raise SystemExit(f"{path.name}: front matter needs {field}")
    if not SLUG_RE.match(slug):
        raise SystemExit(f"{path.name}: slug must be lowercase letters, digits and dashes: {slug!r}")
    if not DATE_RE.match(date):
        raise SystemExit(f"{path.name}: date must be YYYY-MM-DD: {date!r}")
    body = m.group(2).strip()
    cjk = len(CJK_RE.findall(body))
    words = len(WORD_RE.findall(body))
    return {
        "slug": slug,
        "title": meta["title"],
        "title_en": meta.get("title_en", ""),
        "date": date,
        "summary": meta["summary"],
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "minutes": max(1, round(cjk / 400 + words / 220)),
        "body_html": render_markdown(body),
    }


def load_posts() -> list[dict]:
    if not POSTS_DIR.is_dir():
        return []
    posts = [p for p in (parse_post(path) for path in sorted(POSTS_DIR.glob("*.md"))) if p]
    seen: set[str] = set()
    for post in posts:
        if post["slug"] in seen:
            raise SystemExit(f"duplicate blog slug {post['slug']}")
        seen.add(post["slug"])
    return sorted(posts, key=lambda p: (p["date"], p["slug"]), reverse=True)


def page(title: str, body: str, description: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-page="blog" data-root="../">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="{CSP}" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="theme-color" content="#0F1110" />
  <meta name="description" content="{esc(description)}" />
  <title>{esc(title)} · AI Radar</title>
  <link rel="icon" href="../assets/logo.png" />
  <link rel="stylesheet" href="../assets/radar.css" />
  <link rel="alternate" type="application/rss+xml" title="AI Radar 订阅" href="../feed.xml" />
</head>
<body>
  <div class="app">
    <script src="../assets/safe-href.js"></script>
    <script src="../assets/shell.js"></script>
    <div class="content">
{body}
    </div>
  </div>
</body>
</html>
"""


FOOTER = f"""        <footer class="site-footer">
          <p class="motto">给迷途者的代码，给觉醒者的诗。<span class="en">Code for the lost, poetry for the awake.</span></p>
          <p>随笔是编者个人观点，不是信号，也不构成投资或采购建议。</p>
          <p>更正与下架：请通过「<a href="{FEEDBACK_FORM}" target="_blank" rel="noopener noreferrer">反馈 / 建议</a>」告知。</p>
          <p>内容以 CC BY-NC 4.0 发布，转载请署名并链回原文。</p>
        </footer>"""


def tags_html(post: dict) -> str:
    return "".join(f'<span class="tag prac">{esc(t)}</span>' for t in post["tags"])


def render_index(posts: list[dict]) -> str:
    if posts:
        rows = "\n".join(
            f"""          <li><a href="./{esc(p['slug'])}.html">
            <p class="post-meta"><time datetime="{esc(p['date'])}">{esc(p['date'])}</time><span>约 {p['minutes']} 分钟</span>{tags_html(p)}</p>
            <h2>{esc(p['title'])}{f'<span class="en">{esc(p["title_en"])}</span>' if p['title_en'] else ''}</h2>
            <p>{esc(p['summary'])}</p>
          </a></li>"""
            for p in posts
        )
        listing = f'        <ul class="post-list">\n{rows}\n        </ul>'
    else:
        listing = '        <p class="empty">还没有随笔。第一篇写好后会出现在这里。</p>'
    body = f"""      <main id="main">
        <p class="eyebrow">共鸣 · Resonance</p>
        <h1>随笔<span class="en">Notes</span></h1>
        <p class="sub">信号之外，编者想多说几句的地方：为什么这样筛、怎么用这些工具、做这个站时想明白的事。不追热点，写完才发。</p>
{listing}
{FOOTER}
      </main>"""
    return page("随笔", body, "AI Radar 编者随笔：筛选方法、工具用法与做站笔记。")


def render_post(post: dict, newer: dict | None, older: dict | None) -> str:
    nav = []
    nav.append(f'<a href="./{esc(older["slug"])}.html">← {esc(older["title"])}</a>' if older else "<span></span>")
    nav.append(f'<a href="./{esc(newer["slug"])}.html">{esc(newer["title"])} →</a>' if newer else '<a href="./">全部随笔</a>')
    en = f'<span class="en">{esc(post["title_en"])}</span>' if post["title_en"] else ""
    body = f"""      <main id="main">
        <article>
          <header class="post-head">
            <p class="eyebrow"><a href="./">随笔 · Notes</a></p>
            <h1>{esc(post['title'])}{en}</h1>
            <p class="post-meta"><time datetime="{esc(post['date'])}">{esc(post['date'])}</time><span>约 {post['minutes']} 分钟</span>{tags_html(post)}</p>
          </header>
          <div class="prose">
{post['body_html']}
          </div>
        </article>
        <nav class="post-nav" aria-label="上一篇与下一篇">{''.join(nav)}</nav>
{FOOTER}
      </main>"""
    return page(post["title"], body, post["summary"])


def write_if_changed(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build() -> list[dict]:
    posts = load_posts()
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    write_if_changed(BLOG_DIR / "index.html", render_index(posts))
    for i, post in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        write_if_changed(BLOG_DIR / f"{post['slug']}.html", render_post(post, newer, older))
    keep = {f"{p['slug']}.html" for p in posts} | {"index.html"}
    for path in BLOG_DIR.glob("*.html"):
        if path.name not in keep:
            path.unlink()
    doc = {
        "schema_version": 1,
        "updated": posts[0]["date"] if posts else "",
        "note": "编者随笔。观点不是信号；源文件在 content/posts/。",
        "posts": [
            {
                "slug": p["slug"],
                "title": p["title"],
                "title_en": p["title_en"],
                "date": p["date"],
                "summary": p["summary"],
                "tags": p["tags"],
                "minutes": p["minutes"],
                "url": SITE + f"blog/{p['slug']}.html",
            }
            for p in posts
        ],
    }
    write_if_changed(BLOG_DIR / "posts.json", json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return posts


def self_check() -> None:
    evil = render_markdown(
        "<script>alert(1)</script>\n\n"
        "[x](javascript:alert(1)) [y](//evil.test/a) [z](data:text/html,1)\n\n"
        '[ok](https://example.com/a?b=1&c=2) [in](../today.html) [q](https://e.test/"onmouseover=1)\n\n'
        "```\n<img src=x onerror=alert(2)>\n```\n\n"
        "**<b>bold</b>** `<i>code</i>`"
    )
    assert "<script" not in evil and "<img" not in evil and "<b>" not in evil and "<i>" not in evil, evil
    assert 'href="javascript' not in evil and 'href="//' not in evil and 'href="data' not in evil, evil
    assert '<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">ok</a>' in evil, evil
    assert '<a href="../today.html">in</a>' in evil, evil
    assert 'href="https://e.test/' not in evil, evil
    assert "&lt;script&gt;" in evil and "&lt;img src=x" in evil, evil

    blocks = render_markdown("## 标题\n\n第一段\n接着\n\n- 一\n- 二\n\n1. 甲\n2. 乙\n\n> 引用\n\n---\n\n### 小节")
    for needle in ("<h2>标题</h2>", "<p>第一段 接着</p>", "<ul><li>一</li><li>二</li></ul>",
                   "<ol><li>甲</li><li>乙</li></ol>", "<blockquote><p>引用</p></blockquote>", "<hr />", "<h3>小节</h3>"):
        assert needle in blocks, (needle, blocks)
    assert render_markdown("# 一级").startswith("<h2>"), "post body h1 must render as h2; the title is the h1"
    print("blog self-check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    posts = build()
    print(f"  blog: {len(posts)} posts → public/blog/")


if __name__ == "__main__":
    main()
