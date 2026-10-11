# scripts/

| Script | Role |
|--------|------|
| `migrate_cards.py` | Legacy cards → schema_version 2 (idempotent) |
| `generate_derived.py` | archive → items/feed/lens feeds/tools-radar/today3 |
| `validate.py` | Schema + archive monotonic vs origin/main + feed count |
| `generate_weekly_memo.py` | Draft weekly decision memo under `public/memos/` |
| `score_sources.py` | Source scoreboard → `public/source-scores.json` |
| `feishu_notify.py` | Formal P0 + 24h health (needs `FEISHU_BOT_WEBHOOK`; state in `.feishu-notify-state.json`) |
| `sync_root_pages.py` | Interim mirror public/ → repo root for legacy Pages. Skips README.md. Stops when `.no-root-mirror` exists |
| `retire_root_mirrors.py` | Delete root mirrors after Pages source is GitHub Actions |

```bash
pip install -r requirements-ci.txt
python3 scripts/generate_derived.py
python3 scripts/validate.py
```

Repo-root `generate_feed.py` derives and, until mirrors are retired, syncs the legacy Pages root.
