# AI Radar · 决策信号系统

把「情报时间线」升级为可行动、可证伪的决策信号。

- 看板：https://ruiyaoe-hash.github.io/ai-radar/
- RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml
- 工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html
- 卡片规范：[`CARD_SPEC.md`](./CARD_SPEC.md)
- Alba 例程：[`TIMELINE.md`](./TIMELINE.md)
- 全量规格：[`docs/DECISION-SIGNAL-FULL-SPEC.md`](./docs/DECISION-SIGNAL-FULL-SPEC.md)
- 验收清单：[`docs/DECISION-SIGNAL-CHECKLIST.md`](./docs/DECISION-SIGNAL-CHECKLIST.md)

## 成功是什么样子

主人每周因 Radar 做出至少 **N=3** 个工具或赛道决策；P0 事后命中率目标先写 **「待校准」**（X）；重大发布首报时差目标 **&lt; Y=6 小时**。N/X/Y 可在 `config.json` → `success_metrics` 调整。

北极星指标：**可行动信号数**（卡片上的主人 `action`：`tried` / `thesis_updated` / `shared` / `ignored`），每周回看。

## 单源真相

| 路径 | 用途 |
|------|------|
| `public/archive/YYYY-MM-DD.json` | **唯一写入源**（Alba 只追加/更新当日卡并 commit） |
| `public/items.json` 等 | CI / `scripts/generate_derived.py` 派生 |
| `public/` | GitHub Pages 发布根（Actions `deploy-pages`） |

根目录 `items.json` / `feed.xml` / `archive/` 与 `data/` 三份副本策略已废弃。

## 本地命令

```bash
python3 scripts/migrate_cards.py      # 旧卡 → 事件模型（幂等）
python3 scripts/generate_derived.py   # 或 python3 generate_feed.py
python3 scripts/validate.py
python3 scripts/score_sources.py
python3 scripts/generate_weekly_memo.py
python3 scripts/feishu_notify.py      # 无 webhook 时 dry-run
```

本地预览：在 `public/` 下起静态服，例如 `python3 -m http.server 8080 --directory public`。

## Secrets（可选）

在仓库 Settings → Secrets 配置 `FEISHU_BOT_WEBHOOK`（飞书自定义机器人 webhook）。  
未配置时 Actions 仍跑校验与部署；推送正式 P0 / 24h 健康告警为 dry-run。详见 [`docs/FEISHU.md`](./docs/FEISHU.md)。

## Pages

Settings → Pages → Source = **GitHub Actions**（本仓库 `deploy-pages.yml` 上传 `public/`）。
