#!/usr/bin/env python3
"""Regenerate public/feed.xml from public/items.json for GitHub Pages."""
import json, html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import format_datetime

ROOT = Path(__file__).resolve().parent
items_path = ROOT / 'public' / 'items.json'
out = ROOT / 'public' / 'feed.xml'
site = 'https://ruiyaoe-hash.github.io/ai-radar/'
feed_url = site + 'feed.xml'
TZ = timezone(timedelta(hours=8))
now = datetime.now(TZ)

def parse_item_time(s: str):
    try:
        mm, dd_rest = s.split('-', 1)
        dd, hm = dd_rest.split(' ', 1)
        hh, mi = hm.split(':')
        return datetime(now.year, int(mm), int(dd), int(hh), int(mi), tzinfo=TZ)
    except Exception:
        return now

def esc(t):
    return html.escape(t or '', quote=True)

data = json.loads(items_path.read_text(encoding='utf-8'))
parts = ['<?xml version="1.0" encoding="UTF-8"?>',
 '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
 '<channel>',
 f'<title>{esc("AI Radar · Alba")}</title>',
 f'<link>{esc(site)}</link>',
 f'<description>{esc("Alba AI Radar：A 级 X 信源提炼（P0/P1），给人看看板、给 Agent 订阅。")}</description>',
 '<language>zh-cn</language>',
 f'<lastBuildDate>{esc(format_datetime(now))}</lastBuildDate>',
 f'<atom:link href="{esc(feed_url)}" rel="self" type="application/rss+xml"/>']
for it in data.get('items', []):
    title = f"[{it.get('priority','')}/{it.get('tag','')}] {it.get('title','')}"
    link = it.get('url') or site
    bullets = it.get('bullets') or []
    desc = '<br/>'.join(f'• {esc(b)}' for b in bullets)
    handle = it.get('handle') or ''
    if handle:
        desc += f'<br/>来源 @{esc(handle)}'
    pub = parse_item_time(it.get('time') or '')
    parts += ['<item>',
      f'<title>{esc(title)}</title>',
      f'<link>{esc(link)}</link>',
      f'<guid isPermaLink="true">{esc(link)}</guid>',
      f'<pubDate>{esc(format_datetime(pub))}</pubDate>',
      f'<description><![CDATA[{desc}]]></description>',
      '</item>']
parts += ['</channel>', '</rss>', '']
out.write_text('\n'.join(parts), encoding='utf-8')
print(f'wrote {out} ({len(data.get("items", []))} items)')
