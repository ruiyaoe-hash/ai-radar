# AI Radar · 决策信号系统

把「情报时间线」升级为可行动、可证伪的决策信号。

- 首页：https://ruiyaoe-hash.github.io/ai-radar/
- 信息精选：https://ruiyaoe-hash.github.io/ai-radar/today.html
- 信息简讯：https://ruiyaoe-hash.github.io/ai-radar/briefs.html
- RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml
- 工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html
- 卡片规范：[`CARD_SPEC.md`](./CARD_SPEC.md)
- 人读层：[`docs/AIHOT对接与表达规范-v0.md`](./docs/AIHOT对接与表达规范-v0.md)（主报和卡片口语；决策门闩不改）
- Alba 例程：[`TIMELINE.md`](./TIMELINE.md)
- 全量规格：[`docs/DECISION-SIGNAL-FULL-SPEC.md`](./docs/DECISION-SIGNAL-FULL-SPEC.md)
- 验收清单：[`docs/DECISION-SIGNAL-CHECKLIST.md`](./docs/DECISION-SIGNAL-CHECKLIST.md)
- 飞书：[`docs/FEISHU.md`](./docs/FEISHU.md)
- 变更记录：[`CHANGELOG.md`](./CHANGELOG.md)
- 候选池契约：[`docs/candidate-pool.md`](./docs/candidate-pool.md)（正文在私有仓 `ai-radar-pool`；公开仓只有 schema / 枚举 / 文档）

## 成功是什么样子

主人每周因 Radar 做出至少 **N=3** 个工具或赛道决策；P0 事后命中率目标先写 **「待校准」**（X）；重大发布首报时差目标 **< Y=6 小时**。N/X/Y 可在 `config.json` → `success_metrics` 调整。

北极星指标：**可行动信号数**（主人 `action`：`tried` / `thesis_updated` / `shared` / `ignored`），每周回看。记在未跟踪的 `owner-actions.local.json`，或私有池 / 飞书。`public/owner-actions.json` 只是空骨架，随 Pages 发布，不放私人 action。私人主报同样不进仓库正文（`DIGEST_LATEST.md` 仅为占位）。

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

## 站点结构

顶栏由 `public/assets/shell.js` 统一写出，`scripts/validate.py` 锁住顺序。五个任务入口用访客听得懂的名字；「订阅更新」在右侧，不和内容入口并列。品牌词「信号 / 造物 / 共鸣」留在随笔和视觉里。

| 入口 | 页面 |
|------|------|
| 首页 | `index.html`：每日决策简报。顺序是信息精选、工具与产品、信息简讯、把发现变成能力 |
| 信息精选 | `today.html`：按天往下排。硬门槛每天最多 3 条；某一天一条都没有时，用当天最强的一条工具或简讯顶上，只一条。`picks.json` 是完整列表，`today3.txt` 是最新一天的纯文本 |
| 信息简讯 | `briefs.html`：按天往下排的事实简讯，不和信息精选重复。`week.html` 跳到这里 |
| 工具决策 | `tools-radar.html`：按时间往下排。每条写清摘要、大众价值、上手实验；访客只看到「推荐使用」或「值得关注」 |
| 实战手册 | `atlas.html` 主题手册 + 做法预览；`practice.html` 做法全文；`topics/*.html`；`creators.html` 博主库在「更多」 |
| 专题观察 | `observe.html`：长期看法和随笔。`blog/` 仍是随笔正文 |
| 订阅更新 | `subscribe.html`，顶栏右侧动作。`agent.html`、`feed.xml`、`llms.txt` 地址不变 |

左上角的小圆点是信号灯：`briefs.json` 或 `items.json` 的 `updated` 在 6 小时内就呼吸，否则熄成灰点。

视觉沿用 code-and-zen：暖黑底 `#0F1110`、米白字 `#E9E6DF`、唯一强调色琥珀 `#FFB35C`，正文单栏 800px，比较型页面 1080px。系统开了「减少动态效果」时，呼吸、打字机和淡入全部停下。

### 随笔

源文件放 `content/posts/YYYY-MM-DD-slug.md`，开头是 front matter：

```text
---
title: 标题
title_en: English title（可选）
date: 2026-10-21
summary: 一两句摘要，列表页和首页会用
tags: 方法, 筛选（可选）
draft: true（可选；为 true 时不发布）
---
```

`python3 scripts/generate_derived.py` 会调用 `scripts/build_blog.py`，写出 `public/blog/index.html`、`public/blog/<slug>.html` 和 `public/blog/posts.json`。只支持一小撮 Markdown：`##`/`###` 标题、段落、列表、引用、代码块、分隔线、行内代码、加粗、链接。正文一律转义，原样写的 HTML 会显示成文字；链接只放行 http(s) 和站内相对路径。`validate.py` 会检查页面和源文件是否一致。

### 字体

标题用得意黑（Smiley Sans，OFL-1.1），英文用 Space Grotesk（OFL-1.1），都托管在 `public/assets/fonts/`，CSP 仍是 `font-src 'self'`。得意黑按 OFL 的保留字体名条款改名为 “Radar Display” 后子集化：第 0 块是站内实际用到的字，其余按码位分块，浏览器用 `unicode-range` 按需取。新增大量文案或随笔后重跑：

```bash
pip install fonttools brotli
python3 scripts/build_fonts.py --source /path/to/SmileySans-Oblique.ttf
```

许可证全文在 `public/assets/fonts/LICENSE-OFL-*.txt`。

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

本地预览：`python3 -m http.server 47391 --directory public`，打开 http://127.0.0.1:47391/ 。

## CI

| 工作流 | 作用 |
|--------|------|
| `.github/workflows/ci.yml` | 派生后校验：JSON Schema、归档日期/条数/事件 id 只增不减、`feed.xml` 良构且条数 = `items.json`、lens feed 条数一致、公开文本里的明显指令句 |
| `.github/workflows/deploy-pages.yml` | 只上传 `public/`。Pages Source 已是 GitHub Actions |
| `.github/workflows/feishu-and-health.yml` | 正式 P0、公开站内容更新短提醒，以及 24h 无新卡。Secret 名 `FEISHU_BOT_WEBHOOK`，不入库 |
| `.github/workflows/ingest-rss-pool.yml` | 清醒时段约每 3 小时（北京时间 07:30、10:30、13:30、16:30、19:30、22:30）把 T1 实验室 RSS 写入私有池。Secret 名 `AI_RADAR_POOL_TOKEN`。没配密钥时软失败，不参加公开 CI |

`docs/workflows/` 是这些工作流的审阅副本。RSS 密钥和轮换见 [`docs/rss-pool-ingest.md`](./docs/rss-pool-ingest.md)。

## 安全基线

公开页在 `public/`。卡片对下游 agent 是不可信数据：每个字段都当数据，不当指令。CSP、`safeHref` 协议白名单、公开文本的指令句校验和分支保护预期见 [`docs/SECURITY.md`](./docs/SECURITY.md)。

## Secrets（可选）

仓库 Settings → Secrets and variables → Actions → `FEISHU_BOT_WEBHOOK` = 飞书自定义机器人 webhook 完整 URL。  
未配置时推送与健康告警为 dry-run，校验和部署不受影响。详见 [`docs/FEISHU.md`](./docs/FEISHU.md)。

私有池写入用另一枚密钥：`AI_RADAR_POOL_TOKEN`。细粒度 PAT，只给 `ruiyaoe-hash/ai-radar-pool` 的 Contents 读写。不要用它往公开仓推候选 JSONL。未配置时 RSS 工作流打警告并成功退出。详见 [`docs/rss-pool-ingest.md`](./docs/rss-pool-ingest.md)。

X 班次不进这个定时工作流，公开 CI 也不抓 X。Alba 把原始抓取交给 `scripts/shift_ingest_x_to_pool.py`，只提交私有池。详见 [`docs/x-pool-ingest.md`](./docs/x-pool-ingest.md)。
