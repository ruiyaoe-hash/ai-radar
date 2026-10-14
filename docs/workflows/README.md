# workflows

Canonical copies live in [`.github/workflows/`](../../.github/workflows/).  
Files in this directory are review copies of the same YAML (kept so the workflow text is visible even when a token cannot push `.github/workflows/`).

Edit `.github/workflows/` first, then copy here.

`ops-retract.yml` is a dry-run `workflow_dispatch`（撤稿 / 暂停班次）。它不提交、不删归档、不调用飞书。手册：`docs/runbook-retract.md`。
