# public/ — GitHub Pages 根目录

公开内容已于 2026-10-23 清空，原文在 `retained/pre-auto-reset-2026-10-23/`；此后由全自动班次重新填充。

- **写入源**：`archive/YYYY-MM-DD.json`（Alba append-only）
- **派生**：`items.json`、`picks.json`、`feed.xml`、`feeds/`、`tools-radar.json`、`today3.txt`、`source-scores.json`、`memos/`（由 `scripts/generate_derived.py` / CI）
- **`owner-actions.json`**：公开空骨架。私人 action 不写在这里，Pages 上不应出现主人的实时动作
- **信息精选**：`picks.json`，硬门槛下每个上海日历日最多 3 条。某一天一条都没有时，用当天最强的一条工具或简讯顶上，只一条，不改成重磅，也不放宽多源门槛去凑第二条。历史不截断。`today3.txt` 只保留最新一天的纯文本
- **信息简讯**：`briefs.json`。标题和摘要必须是中文。和信息精选、做法、领域进展的链接不重复
- **博主实操**：写清步骤才会出现。班次打分后，`scripts/project_public_lanes.py` 把过了做法门的私有池行写成 `practice/inbox/`（至少两步中文做法）。收藏数只用来排序，收藏少不会单独丢掉一条还能照做的做法。编号、首先/然后，或一段连续写成的操作说明，只要能拆成两步具体动作都算。短回复和空话不算。标题为空时用正文第一句做临时标题，再走中文编辑；英文只要能把事情说清楚即可，编辑脚手架和待办仍然不上站。英文步骤本身仍然不上。跟大家同步、没想到搞好了这类状态句不当标题；步骤还能照做时改写成做法标题，不把整卡丢掉。派生脚本再写入 `practice.json`。同一 id 不重复写。版式示例在 `practice.sample.json`（页面 `?sample=1`）
- **领域进展**：`data/watch.json`。同一脚本把非实操、非快讯的分析行写成专题观察。标题为空时同样用正文第一句补上。写不清、或仍是英文的，不会出现。主题手册没有素材时保持空列表，不预造主题骨架；长期看法和随笔仍由人写
- **实战图谱**：编辑维护 `data/atlas.source.json`（方向、主题手册、原帖、博主）。派生脚本写出 `data/kb.json` 和四份拆分，以及 `topics/<slug>.html`。每条已上站的实操 id 必须出现在 sources 里，否则派生失败。没有原帖的主题状态是待采集。需求信号来自 `data/demand.json` 的最近一次滚动，不是冻住的裸比值。主题建议在 `data/topic-suggestions.json`；`verified` 不是 true 时不写手册。
- **Agent 发现**：`agent.html`、`llms.txt`、`schemas/`（公开 feed 的 JSON Schema 与 CHANGELOG）。候选池的 schema 不在这个目录。
- **随笔**：源文件在仓库根的 `content/posts/*.md`，派生脚本写出 `blog/index.html`、`blog/<slug>.html`、`blog/posts.json`。不要手改 `blog/` 里的文件。
- **字体**：`assets/fonts/` 由 `scripts/build_fonts.py` 生成（得意黑子集改名 Radar Display、Space Grotesk），OFL 许可证同目录。
- 勿在仓库根目录再维护镜像副本。
