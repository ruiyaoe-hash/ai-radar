# public/ — GitHub Pages 根目录

- **写入源**：`archive/YYYY-MM-DD.json`（Alba append-only）
- **派生**：`items.json`、`feed.xml`、`feeds/`、`tools-radar.json`、`today3.txt`、`source-scores.json`、`memos/`（由 `scripts/generate_derived.py` / CI）
- **`owner-actions.json`**：公开空骨架。私人 action 不写在这里，Pages 上不应出现主人的实时动作
- **博主实操**：编辑精选、每周投放，非自动从监控捞。单条放进 `practice/inbox/` 后跑派生脚本，写入 `practice.json`。版式示例在 `practice.sample.json`（页面 `?sample=1`）
- **实战图谱**：编辑维护 `data/atlas.source.json`（方向、主题手册、原帖、博主）。派生脚本写出 `data/kb.json` 和四份拆分，以及 `topics/<slug>.html`。每条已上站的实操 id 必须出现在 sources 里，否则派生失败。没有原帖的主题状态是待采集。需求信号来自 `data/demand.json` 的最近一次滚动，不是冻住的裸比值。主题建议在 `data/topic-suggestions.json`；`verified` 不是 true 时不写手册。
- **Agent 发现**：`agent.html`、`llms.txt`、`schemas/`（公开 feed 的 JSON Schema 与 CHANGELOG）。候选池的 schema 不在这个目录。
- **随笔**：源文件在仓库根的 `content/posts/*.md`，派生脚本写出 `blog/index.html`、`blog/<slug>.html`、`blog/posts.json`。不要手改 `blog/` 里的文件。
- **字体**：`assets/fonts/` 由 `scripts/build_fonts.py` 生成（得意黑子集改名 Radar Display、Space Grotesk），OFL 许可证同目录。
- 勿在仓库根目录再维护镜像副本。
