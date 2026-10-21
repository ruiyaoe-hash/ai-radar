# workflows

Canonical copies live in [`.github/workflows/`](../../.github/workflows/).  
Files in this directory are review copies of the same YAML (kept so the workflow text is visible even when a token cannot push `.github/workflows/`).

Edit `.github/workflows/` first, then copy here.

`ops-retract.yml` is a dry-run `workflow_dispatch`（撤稿 / 暂停班次）。它不提交、不删归档、不调用飞书。手册：`docs/runbook-retract.md`。

`ingest-rss-pool.yml` 把 T1 实验室 RSS 写入私有仓 `ai-radar-pool`，接着打分，并把自动档快讯推回公开仓的 `public/briefs.json`。公开 PR 的 CI 不跑它。密钥 `AI_RADAR_POOL_TOKEN` 没配时软失败。手册：`docs/rss-pool-ingest.md`、`docs/score-and-briefs.md`。

`ingest-x-pool.yml` 是 X 关注池定时抓取。`X_BEARER_TOKEN` 没配时不请求 X，手灌路径仍可用。手册：`docs/x-pool-ingest.md`。

两个 ingest 工作流共用 `concurrency: pool-writer`，推快讯前跑 `validate.py`，推送成功后显式触发 `deploy-pages.yml`。所有 `uses:` 锁 commit SHA，`validate.py` 会检查本目录与 `.github/workflows/` 逐字一致。
