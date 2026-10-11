# AI Radar 时间线例程（给 Alba）· append-only archive

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
规范：`CARD_SPEC.md`（schema_version 2）

## 原则

1. **只写** `public/archive/YYYY-MM-DD.json`（追加或按 `id`/`url` 更新原卡）
2. **不要**手改 `items.json` / `feed.xml` / 根镜像（已废除）
3. commit + push `main` → GitHub Actions：校验、派生、部署 `public/`

## 每次 digest（08:00 / 13:30 北京）

1. **写卡片**（事件模型）  
   - 生成 `id = evt-YYYYMMDD-slug`  
   - 填 `status` / `sources[{url,handle,role}]` / `lens` / `objective`  
   - rumor 不得当正式 P0；有判断则写带 `falsifier` 的 `so_what`，否则省略  
   - **不要**写 `bullets`

2. **合并当日归档**  
   - 路径：`public/archive/YYYY-MM-DD.json`  
   - 按 `id`（或 url）去重；升级传闻时更新原卡并写 `correction`  
   - `count` = `len(items)`；`schema_version: 2`

3. **本地可选派生（调试）**  
   ```bash
   python3 generate_feed.py
   # 等同 python3 scripts/generate_derived.py
   python3 scripts/validate.py
   ```

4. **提交并推送**  
   ```bash
   git add public/archive/YYYY-MM-DD.json public/archive/index.json
   # 若本地跑过派生，也可 add 其它 public/ 派生文件；CI 会再生成一遍
   git commit -m "chore: AI Radar digest YYYY-MM-DD HH:MM CST"
   git push origin main
   ```

5. **CI 负责**  
   - Schema 校验；归档相对 `main` 只增不减  
   - 派生 `items.json`、`archive/index.json`、`feed.xml`、`feeds/lens-*.xml`、`tools-radar.json`、`today3.txt`、周报草稿  
   - `deploy-pages` 只发 `public/`  
   - 可选：正式 P0 + 24h 健康 → Feishu（secret `FEISHU_BOT_WEBHOOK`）

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
- Pages 来自 Actions，不再依赖仓库根目录镜像
