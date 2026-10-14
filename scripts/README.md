# scripts/

| Script | Role |
|--------|------|
| `card_times.py` | `published_at` / `ingested_at`（ISO-8601 UTC）。首次写入才盖 `ingested_at`；`published_at` 只从信源时间来，不猜 |
| `migrate_cards.py` | Legacy cards → schema_version 2 (idempotent). Stamps ingest time only when materializing a new v2 card |
| `generate_derived.py` | archive → items/feed/lens feeds/tools-radar/today3；若 `public/practice/inbox/` 有 JSON 则并入 `practice.json` |
| `validate.py` | Schema + archive monotonic vs origin/main + feed count + pool-contract fixtures |
| `ingest_x.py` | Raw X fetch JSON → candidate JSONL (all items, stable cid). Judgment fields stay empty |
| `generate_weekly_memo.py` | Draft weekly decision memo under `public/memos/` |
| `score_sources.py` | Source scoreboard → `public/source-scores.json` |
| `feishu_notify.py` | Formal P0 + 24h health (needs `FEISHU_BOT_WEBHOOK`; state in `.feishu-notify-state.json`) |
| `ops_retract.py` | Dry-run retract/pause lookup. Does not edit archive, git, or Feishu. See `docs/runbook-retract.md` |
| `sync_root_pages.py` | Interim mirror public/ → repo root for legacy Pages. Skips README.md. Stops when `.no-root-mirror` exists |
| `retire_root_mirrors.py` | Delete root mirrors after Pages source is GitHub Actions |

```bash
pip install -r requirements-ci.txt
python3 scripts/generate_derived.py
python3 scripts/validate.py
```

Repo-root `generate_feed.py` derives `public/` and skips the legacy root mirror while `.no-root-mirror` exists.
