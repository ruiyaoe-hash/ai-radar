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

## state.json（2026-10-14 核实：弃）

仓库根的 `state.json` 仍有 `watermark`、`last_run`、`seen_ids`、`last_digest`。这四项停在 **2026-10-12T05:35:03Z**，`last_digest` 仍是 `2026-10-12 13:30 CST main`。

其后的 digest 没有改它：`public/archive/2026-10-13.json`、`public/archive/2026-10-14.json` 和 `DIGEST_LATEST.md`（2026-10-14 08:00）都已发布。`scripts/` 里没有读写这份水位的例程。`scripts/feishu_notify.py` 只用 `.feishu-notify-state.json`，并写明不要碰 `state.json`。

**结论：弃。** 文件留着当历史快照，并加了 `contract: deprecated`。它不是去重契约，也不是班次打卡。

下一班 Alba：

- 不要更新 `state.json`，不要用 `seen_ids` 判断「已经报过」
- 去重仍按归档 `id` / `url`（上面的合并步骤）
- 飞书已推送的 id 继续只放在 Actions cache

## 候选池（Phase 1）

筛选留在私有仓 `ai-radar-pool`。公开仓只有 schema、枚举和说明，见 `docs/candidate-pool.md`。

1. 原始 X 抓取不要直接写进公开归档。交给 `scripts/shift_ingest_x_to_pool.py`：全量 `ingest_x`（每一条先是 `pending`，判断字段留空），再 `annotate_gates --only-pending`。不要手写 JSONL。检出、退出码和提交说明见 `docs/x-pool-ingest.md`。
2. 真丢才写 `drop_reason`；`deferred` / `rerouted` 不是丢弃。晋升时公开卡写 `candidate_id`（或 `promotion_path=emergency`），池行再改成 `promoted` 并写 `archive_id`。池 JSONL 只留在私有仓。
3. 北京日历日 **≥ 2026-10-15** 的新归档卡要带 `candidate_id`，或写 `promotion_path=emergency`。更早的卡是遗留，不回填。
4. `derive` 仍只读 `public/archive` 和 practice inbox，不读池。
5. RSS 首批由 Actions `ingest-rss-pool` 写入私有池（密钥 `AI_RADAR_POOL_TOKEN`，只授给 `ai-radar-pool`）。班次扫池里的新 RSS 行，不自动发板。见 `docs/rss-pool-ingest.md`。

## 博主实操

这一栏是编辑精选、每周投放，**非自动从监控捞**。实操向 8 个账号在 `config.json` 的 `practice_handles`，**不要**再用 digest 的 `a_tier` 假装已经覆盖。这 8 个是：`op7418`、`vista8`、`lijigang`、`bcherny`、`trq212`、`mattpocockuk`、`addyosmani`、`ryolu_`。

1. 人工写 `prac-*` JSON，放进 `public/practice/inbox/`
2. `python3 scripts/generate_derived.py` 才会写入 `public/practice.json`
3. 每条要有步骤、可借鉴点和注意。难度、开始前、用时、是否对照原文按 `schemas/practice.schema.json` 的可选字段写

## 撤稿与暂停

见 `docs/runbook-retract.md`。Actions 里的 `Ops · retract or pause (dry-run)` 只查卡、只打印下一步，不改归档、不调飞书。

## 注意

- 人读层按 `docs/AIHOT对接与表达规范-v0.md`（2026-10-16）：主报和 `title` / `objective` / `so_what` 一句一事实，正文不写 `evt-` / `cand-`，跳过清单放附录。决策门闩不改。
- 客观与 so_what **分栏**；无 falsifier 不写 so_what  
- 归档按日累积；看板是滑动窗口（约 7 天 / ≤50 条）  
- 工作流在 `.github/workflows/`。根镜像已退役（`.no-root-mirror`），线上只部署 `public/`
