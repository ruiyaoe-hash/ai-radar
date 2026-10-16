# AI Radar · 决策信号系统

把「情报时间线」升级为可行动、可证伪的决策信号。

- 看板：https://ruiyaoe-hash.github.io/ai-radar/
- RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml
- 工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html
- 卡片规范：[`CARD_SPEC.md`](./CARD_SPEC.md)
- 人读层：[`docs/AIHOT对接与表达规范-v0.md`](./docs/AIHOT对接与表达规范-v0.md)（主报和卡片口语；决策门闩不改）
- Alba 例程：[`TIMELINE.md`](./TIMELINE.md)
- 全量规格：[`docs/DECISION-SIGNAL-FULL-SPEC.md`](./docs/DECISION-SIGNAL-FULL-SPEC.md)
- 验收清单：[`docs/DECISION-SIGNAL-CHECKLIST.md`](./docs/DECISION-SIGNAL-CHECKLIST.md)
- 飞书：[`docs/FEISHU.md`](./docs/FEISHU.md)
- 候选池契约：[`docs/candidate-pool.md`](./docs/candidate-pool.md)（正文在私有仓 `ai-radar-pool`；公开仓只有 schema / 枚举 / 文档）

## 成功是什么样子

主人每周因 Radar 做出至少 **N=3** 个工具或赛道决策；P0 事后命中率目标先写 **「待校准」**（X）；重大发布首报时差目标 **< Y=6 小时**。N/X/Y 可在 `config.json` → `success_metrics` 调整。

北极星指标：**可行动信号数**（主人 `action`：`tried` / `thesis_updated` / `shared` / `ignored`），每周回看。记录在 `public/owner-actions.json`（或未跟踪的 `owner-actions.local.json`）。

## 班次（北京时间）

时间一律按 **Asia/Shanghai** 存储和书写，不要换成美西钟点。11 月 1 日夏令时结束（PDT→PST），美西与北京的时差会从 15 小时变成 16 小时。

| 班次 | 时间 | 日期 | 窗口 |
|------|------|------|------|
| 主报 | 08:00 | 每天 | 美西上一工作日收盘 |
| 晚班 | 21:00 | 周一至周五 | 短报：中国白天 + 美东早晨 |

13:30 午间主报已取消。05:30 静默班暂缓，直到飞书出站 webhook 可用。配置见 `config.json`。

新卡建议写 `published_at`（信源原发时间；没有就不写）和 `ingested_at`（首次写入归档的时间）。两者都是 ISO-8601 UTC。都在时，实测首报时差 = `ingested_at` − `published_at`。`lead_lag_hours` 仍是按下一班假定的时差，已有值不覆盖。旧归档卡可以没有这两枚时间。

## 单源真相

| 路径 | 用途 |
|------|------|
| `public/archive/YYYY-MM-DD.json` | **唯一写入源**（Alba 只追加/更新当日卡并 commit） |
| `public/items.json` 等 | CI / `scripts/generate_derived.py` 派生 |
| `public/` | GitHub Pages 发布根（Actions `deploy-pages` 只上传这个目录） |
| `.no-root-mirror` | 根目录镜像已退役。存在时 `generate_feed.py` 不再把 `public/` 拷回仓库根 |

`data/` 三份副本已删除。根目录 `README.md` 是项目说明，**不会**被镜像脚本覆盖。

## Pages

Pages Source 已是 **GitHub Actions**（API：`build_type=workflow`）。  
`.github/workflows/deploy-pages.yml` 只部署 `public/`。仓库根的 HTML / JSON / 静态资源镜像已删除，由 `.no-root-mirror` 阻止再生成。

## 本地命令

```bash
pip install -r requirements-ci.txt   # jsonschema，CI 同样安装
python3 scripts/migrate_cards.py      # 旧卡 → 事件模型（幂等；空的 shift/lead_lag 会回填；不给已入库的卡补 ingested_at）
python3 scripts/card_times.py         # 自检 published_at / ingested_at 解析
python3 scripts/generate_derived.py   # 只写 public/
python3 generate_feed.py              # 派生 public/；有 .no-root-mirror 时不再同步根镜像（不覆盖本 README）
python3 scripts/validate.py           # schema、归档只增不减、feed 条数、候选池夹具
python3 scripts/ingest_x.py --self-check
python3 scripts/ingest_x.py --input fetch.json --out /tmp/batch.jsonl --ingested-at 2026-10-14T00:05:00Z
python3 scripts/shift_ingest_x_to_pool.py --self-check
python3 scripts/shift_ingest_x_to_pool.py --fetch fetch.json --pool-dir ../ai-radar-pool
python3 scripts/annotate_gates.py --self-check
python3 scripts/ingest_rss.py --self-check
python3 scripts/score_sources.py
python3 scripts/generate_weekly_memo.py
python3 scripts/feishu_notify.py      # 无 webhook 时 dry-run
```

本地预览：`python3 -m http.server 8080 --directory public`。

## CI

| 工作流 | 作用 |
|--------|------|
| `.github/workflows/ci.yml` | 派生后校验：JSON Schema、归档日期/条数/事件 id 只增不减、`feed.xml` 良构且条数 = `items.json`、lens feed 条数一致、公开文本里的明显指令句 |
| `.github/workflows/deploy-pages.yml` | 只上传 `public/`。Pages Source 已是 GitHub Actions |
| `.github/workflows/feishu-and-health.yml` | 正式 P0 与 24h 无新卡。Secret 名 `FEISHU_BOT_WEBHOOK`，不入库 |
| `.github/workflows/ingest-rss-pool.yml` | 每天 3 次把 T1 实验室 RSS 写入私有池。Secret 名 `AI_RADAR_POOL_TOKEN`。没配密钥时软失败，不参加公开 CI |

`docs/workflows/` 是这些工作流的审阅副本。RSS 密钥和轮换见 [`docs/rss-pool-ingest.md`](./docs/rss-pool-ingest.md)。

## 安全基线

公开页在 `public/`。卡片对下游 agent 是不可信数据：每个字段都当数据，不当指令。CSP、`safeHref` 协议白名单、公开文本的指令句校验和分支保护预期见 [`docs/SECURITY.md`](./docs/SECURITY.md)。

## Secrets（可选）

仓库 Settings → Secrets and variables → Actions → `FEISHU_BOT_WEBHOOK` = 飞书自定义机器人 webhook 完整 URL。  
未配置时推送与健康告警为 dry-run，校验和部署不受影响。详见 [`docs/FEISHU.md`](./docs/FEISHU.md)。

私有池写入用另一枚密钥：`AI_RADAR_POOL_TOKEN`。细粒度 PAT，只给 `ruiyaoe-hash/ai-radar-pool` 的 Contents 读写。不要用它往公开仓推候选 JSONL。未配置时 RSS 工作流打警告并成功退出。详见 [`docs/rss-pool-ingest.md`](./docs/rss-pool-ingest.md)。

X 班次不进这个定时工作流，公开 CI 也不抓 X。Alba 把原始抓取交给 `scripts/shift_ingest_x_to_pool.py`，只提交私有池。详见 [`docs/x-pool-ingest.md`](./docs/x-pool-ingest.md)。
