# AI Radar 时间线例程（给 Alba）· append-only archive

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
规范：`CARD_SPEC.md`（schema_version 2）

## 原则

1. **只写** `public/archive/YYYY-MM-DD.json`（追加或按 `id`/`url` 更新原卡）
2. **不要**手改 `public/items.json` / `feed.xml`，也不要在仓库根重建镜像（`.no-root-mirror` 已退役）
3. commit + push `main` → GitHub Actions：校验、派生、部署 `public/`

## 每次 digest（北京时间 Asia/Shanghai）

不要用美西钟点排班。11 月 1 日 PDT→PST，与北京的时差从 15 小时变成 16 小时。

| 班次 | 时间 | 日期 | 窗口 |
|------|------|------|------|
| 主报 | 08:00 | 每天 | 美西上一工作日收盘 |
| 晚班 | 21:00 | 周一至周五 | 短报：中国白天 + 美东早晨 |

13:30 午间已取消，不再当主报。05:30 静默班暂缓，直到飞书出站 webhook 可用。

1. **写卡片**（事件模型）  
   - 生成 `id = evt-YYYYMMDD-slug`  
   - 填 `status` / `sources[{url,handle,role}]` / `lens` / `objective`  
   - 新卡写 `ingested_at` = 此刻 UTC（ISO-8601，如 `2026-10-13T00:00:00Z`）。按 `id` 更新原卡时不要改它  
   - `published_at` 只在信源有时间时写：X 用 `created_at`，RSS 用 `pubDate`，转成 UTC。没有时间就省略，不要猜  
   - 已有的 `lead_lag_hours` / `lead_lag_basis` 不动。两枚时间都在时，实测时差 = `ingested_at` − `published_at`  
   - rumor 不得当正式 P0；有判断则写带 `falsifier` 的 `so_what`，否则省略  
   - **不要**写 `bullets`  
   - 需要解析信源时间时用 `scripts/card_times.py` 的 `stamp_first_report`（`python3 scripts/card_times.py` 可自检）

2. **合并当日归档**  
   - 路径：`public/archive/YYYY-MM-DD.json`  
   - 按 `id`（或 url）去重；升级传闻时更新原卡并写 `correction`  
   - `count` = `len(items)`；`schema_version: 2`

3. **本地派生**  
   ```bash
   python3 generate_feed.py
   # = scripts/generate_derived.py；.no-root-mirror 存在时跳过根目录镜像
   pip install -r requirements-ci.txt
   python3 scripts/validate.py
   ```
   需要 `jsonschema` 才能跑校验。归档相对上一提交只增不减（日期与事件 id）。

4. **提交并推送**  
   ```bash
   git add public/archive/YYYY-MM-DD.json public/
   git commit -m "chore: AI Radar digest YYYY-MM-DD HH:MM CST"
   git push origin main
   ```
   不要提交 `.feishu-notify-state.json`，也不要提交仓库根的 HTML/JSON 镜像。CI 会再派生并校验一遍。

5. **CI 负责**（`.github/workflows/`）  
   - Schema（`schemas/*.json`）；归档相对基线只增不减（日期、条数、事件 id）  
   - `feed.xml` 良构且条数 = `items.json`；lens feed 条数与看板一致  
   - 派生 `items.json`、`archive/index.json`、`feed.xml`、`feeds/lens-*.xml`、`tools-radar.json`、`today3.txt`、周报草稿  
   - `deploy-pages` 只上传 `public/`。Pages Source 已是 GitHub Actions  
   - 正式 P0 + 24h 健康 → Feishu（secret `FEISHU_BOT_WEBHOOK`，未配置则 dry-run）

## 目录约定

| 路径 | 用途 |
|------|------|
| `public/archive/*.json` | 按日全量（唯一写入源） |
| `public/items.json` | 看板窗口（派生） |
| `public/index.html` | 决策信号 UI（lens / P0-待证 / 今日3条） |
| `public/tools-radar.html` | 工具雷达 |
| `public/theses.json` | 长期论点 |
| `public/owner-actions.json` | 主人 action（注意隐私） |
| `public/config/sources.json` | 一手信源清单 |
| `schemas/` | JSON Schema |
| `scripts/` | migrate / derive / validate / memo / score / feishu |

## 注意

- 客观与 so_what **分栏**；无 falsifier 不写 so_what  
- 归档按日累积；看板是滑动窗口（约 7 天 / ≤50 条）  
- 工作流在 `.github/workflows/`。根镜像已退役（`.no-root-mirror`），线上只部署 `public/`
