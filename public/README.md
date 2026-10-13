# public/ — GitHub Pages 根目录

- **写入源**：`archive/YYYY-MM-DD.json`（Alba append-only）
- **派生**：`items.json`、`feed.xml`、`feeds/`、`tools-radar.json`、`today3.txt`、`source-scores.json`、`memos/`（由 `scripts/generate_derived.py` / CI）
- **博主实操**：`practice.json` 默认为空。单条放进 `practice/inbox/` 后跑派生脚本。版式示例在 `practice.sample.json`（页面 `?sample=1`）
- 勿在仓库根目录再维护镜像副本。
