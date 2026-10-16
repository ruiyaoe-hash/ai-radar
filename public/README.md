# public/ — GitHub Pages 根目录

- **写入源**：`archive/YYYY-MM-DD.json`（Alba append-only）
- **派生**：`items.json`、`feed.xml`、`feeds/`、`tools-radar.json`、`today3.txt`、`source-scores.json`、`memos/`（由 `scripts/generate_derived.py` / CI）
- **博主实操**：编辑精选、每周投放，非自动从监控捞。单条放进 `practice/inbox/` 后跑派生脚本，写入 `practice.json`。版式示例在 `practice.sample.json`（页面 `?sample=1`）
- **Agent 发现**：`agent.html`、`llms.txt`、`schemas/`（公开 feed 的 JSON Schema 与 CHANGELOG）。候选池的 schema 不在这个目录。
- 勿在仓库根目录再维护镜像副本。
