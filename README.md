# AI Radar · 决策信号系统

把「情报时间线」升级为可行动、可证伪的决策信号。

- 看板：https://ruiyaoe-hash.github.io/ai-radar/
- RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml
- 工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html
- 卡片规范：[`CARD_SPEC.md`](./CARD_SPEC.md)
- Alba 例程：[`TIMELINE.md`](./TIMELINE.md)
- 全量规格：[`docs/DECISION-SIGNAL-FULL-SPEC.md`](./docs/DECISION-SIGNAL-FULL-SPEC.md)
- 验收清单：[`docs/DECISION-SIGNAL-CHECKLIST.md`](./docs/DECISION-SIGNAL-CHECKLIST.md)
- 飞书：[`docs/FEISHU.md`](./docs/FEISHU.md)

## 成功是什么样子

主人每周因 Radar 做出至少 **N=3** 个工具或赛道决策；P0 事后命中率目标先写 **「待校准」**（X）；重大发布首报时差目标 **< Y=6 小时**。N/X/Y 可在 `config.json` → `success_metrics` 调整。

北极星指标：**可行动信号数**（主人 `action`：`tried` / `thesis_updated` / `shared` / `ignored`），每周回看。记录在 `public/owner-actions.json`（或未跟踪的 `owner-actions.local.json`）。

## 单源真相

| 路径 | 用途 |
|------|------|
| `public/archive/YYYY-MM-DD.json` | **唯一写入源**（Alba 只追加/更新当日卡并 commit） |
| `public/items.json` 等 | CI / `scripts/generate_derived.py` 派生 |
| `public/` | GitHub Pages 发布根（Actions `deploy-pages` 只上传这个目录） |
| 仓库根 `index.html`、`items.json`、`feed.xml`、`archive/` … | **临时**镜像。Pages 仍从 `main` 的 `/` 发布时，靠它避免看板空白 |

`data/` 三份副本已删除。根目录 `README.md` 是项目说明，**不会**被镜像脚本覆盖。

## Pages（还差一次手动切换）

当前站点配置（API）：`build_type=legacy`，source = 分支 `main`、目录 `/`。  
工作流已在 `.github/workflows/deploy-pages.yml`，但在源改成 GitHub Actions 之前，`deploy-pages` 会失败并打印原因；**线上看板仍走根镜像**。

切换顺序：

1. 合并含工作流的提交。
2. Settings → Pages → Build and deployment → Source = **GitHub Actions**。
3. 重跑 **Deploy Pages · public/**，确认 https://ruiyaoe-hash.github.io/ai-radar/ 正常。
4. 再删根镜像（删早了，legacy 发布会 404）：

```bash
python3 scripts/retire_root_mirrors.py --i-switched-pages-to-actions
git add -A && git commit -m "chore: retire legacy Pages root mirror" && git push
```

这会写 `.no-root-mirror`，之后 `generate_feed.py` 不再把 `public/` 拷回根目录。

## 本地命令

```bash
pip install -r requirements-ci.txt   # jsonschema，CI 同样安装
python3 scripts/migrate_cards.py      # 旧卡 → 事件模型（幂等；空的 shift/lead_lag 会回填）
python3 scripts/generate_derived.py   # 只写 public/
python3 generate_feed.py              # 派生 + 刷新根镜像（不覆盖本 README）
python3 scripts/validate.py           # schema、归档只增不减、feed 条数
python3 scripts/score_sources.py
python3 scripts/generate_weekly_memo.py
python3 scripts/feishu_notify.py      # 无 webhook 时 dry-run
```

本地预览：`python3 -m http.server 8080 --directory public`。

## CI

| 工作流 | 作用 |
|--------|------|
| `.github/workflows/ci.yml` | 派生后校验：JSON Schema、归档日期/条数/事件 id 只增不减、`feed.xml` 良构且条数 = `items.json`、lens feed 条数一致 |
| `.github/workflows/deploy-pages.yml` | 只上传 `public/`。Pages 源仍是 legacy 时失败并提示，不覆盖线上 |
| `.github/workflows/feishu-and-health.yml` | 正式 P0 与 24h 无新卡。Secret 名 `FEISHU_BOT_WEBHOOK`，不入库 |

`docs/workflows/` 是这三份文件的审阅副本。

## Secrets（可选）

仓库 Settings → Secrets and variables → Actions → `FEISHU_BOT_WEBHOOK` = 飞书自定义机器人 webhook 完整 URL。  
未配置时推送与健康告警为 dry-run，校验和（在 Pages 源切到 Actions 之后的）部署不受影响。详见 [`docs/FEISHU.md`](./docs/FEISHU.md)。
