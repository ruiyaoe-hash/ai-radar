#!/usr/bin/env python3
"""Regenerate feed.xml from public/items.json for GitHub Pages.

Uses objective bullets as the factual digest. If judgment is present,
appends a clearly labeled 主观判断 section (never mixed into facts).
Also mirrors feed.xml / items.json to repo root so Pages (path=/) works.
"""
import json
import html
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import format_datetime

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
items_path = PUBLIC / 'items.json'
out_public = PUBLIC / 'feed.xml'
out_root = ROOT / 'feed.xml'
site = 'https://ruiyaoe-hash.github.io/ai-radar/'
feed_url = site + 'feed.xml'
TZ = timezone(timedelta(hours=8))
now = datetime.now(TZ)


def parse_item_time(it: dict):
    """Prefer explicit date + time; fall back to MM-DD HH:MM in current year."""
    date = (it.get('date') or '').strip()
    time_s = (it.get('time') or '').strip()
    try:
        if date and time_s and ' ' in time_s:
            hm = time_s.split(' ', 1)[1]  # HH:MM after MM-DD
            hh, mi = hm.split(':')
            y, m, d = date.split('-')
            return datetime(int(y), int(m), int(d), int(hh), int(mi), tzinfo=TZ)
        if date:
            y, m, d = date.split('-')
            return datetime(int(y), int(m), int(d), 12, 0, tzinfo=TZ)
        mm, dd_rest = time_s.split('-', 1)
        dd, hm = dd_rest.split(' ', 1)
        hh, mi = hm.split(':')
        return datetime(now.year, int(mm), int(dd), int(hh), int(mi), tzinfo=TZ)
    except Exception:
        return now


def esc(t):
    return html.escape(t or '', quote=True)


def objective_bullets(it: dict):
    obj = it.get('objective')
    if obj:
        return list(obj)
    return list(it.get('bullets') or [])


def judgment_bullets(it: dict):
    return list(it.get('judgment') or [])


data = json.loads(items_path.read_text(encoding='utf-8'))
parts = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '<channel>',
    f'<title>{esc("AI Radar · Alba")}</title>',
    f'<link>{esc(site)}</link>',
    f'<description>{esc("Alba AI Radar：按日归档的 A 级信源精选。客观摘要与主观判断分栏，关注新工具、新方向、新商业模式。")}</description>',
    '<language>zh-cn</language>',
    f'<lastBuildDate>{esc(format_datetime(now))}</lastBuildDate>',
    f'<atom:link href="{esc(feed_url)}" rel="self" type="application/rss+xml"/>',
]

for it in data.get('items', []):
    title = f"[{it.get('priority', '')}/{it.get('tag', '')}] {it.get('title', '')}"
    link = it.get('url') or site
    obj = objective_bullets(it)
    jud = judgment_bullets(it)
    label = it.get('judgment_label') or '主观判断'

    desc_parts = []
    if obj:
        desc_parts.append('<strong>客观摘要</strong>')
        desc_parts.extend(f'• {esc(b)}' for b in obj)
    if jud:
        desc_parts.append(f'<strong>【{esc(label)}】</strong>')
        desc_parts.extend(f'• {esc(b)}' for b in jud)
    handle = it.get('handle') or ''
    if handle:
        desc_parts.append(f'来源 @{esc(handle)}')
    if it.get('date'):
        desc_parts.append(f'日期 {esc(it["date"])}')
    desc = '<br/>'.join(desc_parts)
    pub = parse_item_time(it)
    parts += [
        '<item>',
        f'<title>{esc(title)}</title>',
        f'<link>{esc(link)}</link>',
        f'<guid isPermaLink="true">{esc(link)}</guid>',
        f'<pubDate>{esc(format_datetime(pub))}</pubDate>',
        f'<description><![CDATA[{desc}]]></description>',
        '</item>',
    ]

parts += ['</channel>', '</rss>', '']
xml = '\n'.join(parts)
out_public.write_text(xml, encoding='utf-8')
out_root.write_text(xml, encoding='utf-8')

# Mirror board + archive to repo root for GitHub Pages (source = /)
(ROOT / 'items.json').write_text(items_path.read_text(encoding='utf-8'), encoding='utf-8')
root_archive = ROOT / 'archive'
root_archive.mkdir(exist_ok=True)
pub_archive = PUBLIC / 'archive'
if pub_archive.is_dir():
    for src in pub_archive.iterdir():
        if src.is_file():
            shutil.copy2(src, root_archive / src.name)

print(f'wrote {out_public} and {out_root} ({len(data.get("items", []))} items)')
