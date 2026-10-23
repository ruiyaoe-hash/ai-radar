# scripts/

| Script | Role |
|--------|------|
| `card_times.py` | `published_at` / `ingested_at`（ISO-8601 UTC）。首次写入才盖 `ingested_at`；`published_at` 只从信源时间来，不猜 |
| `migrate_cards.py` | Legacy cards → schema_version 2 (idempotent). Stamps ingest time only when materializing a new v2 card |
| `human_layer.py` | 人读层：去掉 `evt-` / `cand-`，主报骨架。规则见 `docs/AIHOT对接与表达规范-v0.md`。不改门闩 |
| `generate_derived.py` | archive → items/feed/lens feeds/tools-radar/today3；若 `public/practice/inbox/` 有 JSON 则并入 `practice.json`；`data/atlas.source.json` 与 `data/demand.json` → `data/kb.json` 与 `topics/<slug>.html` |
| `suggest_atlas_topics.py` | 实操候选 → 主题建议。公开清单不写手册；`--apply` 只在 practice 卡 `verified=true` 且确认文件同意时改 `atlas.source.json` |
| `refresh_demand.py` | 滚动图谱收藏/点赞到 `data/demand.json`。平滑比值与打分同一套先验。不改关注名单 |
| `validate.py` | Schema + archive monotonic vs origin/main + feed count + pool-contract fixtures + 公开文本里的明显指令句 |
| `ingest_x.py` | Raw X fetch JSON → candidate JSONL (all items, stable cid). Judgment fields stay empty |
| `shift_ingest_x_to_pool.py` | Alba shift: `ingest_x` then `annotate_gates --only-pending` into a private `--pool-dir`. No X fetch, no promote. Score is the next command |
| `fetch_x_watch.py` | `practice_handles` + `a_tier` → raw fetch JSON when `X_BEARER_TOKEN` is set. Missing token exits 0 and leaves the hand-feed path |
| `score_pool.py` | After gates: v1 rules score (production band), shadow v2, `low_score` trace. Forced P0 stays in review. No network LLM. Optional `review/YYYY-MM-DD.md` and `review/p0-YYYY-MM-DD.json` |
| `score_pool_v2.py` | Experimental multi-axis score. Rules fallback is mandatory. Called from `score_pool.py` |
| `force_p0.py` | Forced P0 matcher (frontier launch, runtime vuln with an upgrade, same-day a_tier pair). Does not publish |
| `card_copy.py` | Card wording next to the score: why watch, evidence label, suggested action, high-priority review flag. No raw scores. Auto briefs only get the official-source sentence |
| `backtest_score_ab.py` | Compare v1 and v2. Chat pack is the labeling path (A or B per item). CSV remains for batch export |
| `derive_briefs.py` | `auto_brief` rows → `public/briefs.json`. Strips raw posts, checks instruction text, skips archive URLs and practice |
| `ingest_rss.py` | Batch-1 lab RSS / GitHub Releases → the same pending rows (`channel=rss`). Live fetch stays out of public CI |
| `annotate_gates.py` | L0 gates + L2 `cluster_id`. Writes judgment fields back. Does not promote. Leaves `low_score` and `editor_skip` in place |
| `generate_weekly_memo.py` | Draft weekly decision memo under `public/memos/` |
| `score_sources.py` | Source scoreboard → `public/source-scores.json`。整数分公式不变。`--pool-dir` 才把丢弃行和收藏÷点赞算进去，那次结果不要提交。公开骨架里的 action 不读 |
| `feishu_notify.py` | Formal P0、公开站更新短提醒、24h health（`FEISHU_BOT_WEBHOOK`；state in `.feishu-notify-state.json`） |
| `ops_retract.py` | Dry-run retract/pause lookup. Does not edit archive, git, or Feishu. See `docs/runbook-retract.md` |
| `sync_root_pages.py` | Interim mirror public/ → repo root for legacy Pages. Skips README.md. Stops when `.no-root-mirror` exists |
| `retire_root_mirrors.py` | Delete root mirrors after Pages source is GitHub Actions |

```bash
pip install -r requirements-ci.txt
python3 scripts/suggest_atlas_topics.py
python3 scripts/refresh_demand.py
python3 scripts/generate_derived.py
python3 scripts/validate.py
```

Repo-root `generate_feed.py` derives `public/` and skips the legacy root mirror while `.no-root-mirror` exists.
