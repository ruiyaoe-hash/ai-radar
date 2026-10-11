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

3. **本地派生（并刷新旧版 Pages 根镜像）**  
   ```bash
   python3 generate_feed.py
   # = scripts/generate_derived.py + 根目录镜像（不覆盖 README.md）
   pip install -r requirements-ci.txt
   python3 scripts/validate.py
   ```
   需要 `jsonschema` 才能跑校验。归档相对上一提交只增不减（日期与事件 id）。

4. **提交并推送**  
   ```bash
   git add public/archive/YYYY-MM-DD.json
   # 旧版 Pages 仍从 main 根目录发布时，把 generate_feed.py 同步出的根镜像一并提交
   git add public/ index.html items.json feed.xml archive/ feeds/ tools-radar.html tools-radar.json today3.txt
   git commit -m "chore: AI Radar digest YYYY-MM-DD HH:MM CST"
   git push origin main
   ```
   不要提交 `.feishu-notify-state.json`。CI 会再派生并校验一遍。

5. **CI 负责**（`.github/workflows/`）  
   - Schema（`schemas/*.json`）；归档相对基线只增不减（日期、条数、事件 id）  
   - `feed.xml` 良构且条数 = `items.json`；lens feed 条数与看板一致  
   - 派生 `items.json`、`archive/index.json`、`feed.xml`、`feeds/lens-*.xml`、`tools-radar.json`、`today3.txt`、周报草稿  
   - `deploy-pages` 只上传 `public/`。Pages 源仍是 legacy `main` `/` 时该工作流会失败并提示去设置里改成 GitHub Actions；改完之前看板仍靠根镜像  
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
- 工作流在 `.github/workflows/`。Pages 源改成 GitHub Actions 之前，根镜像仍要提交；改完并确认部署后，再跑 `scripts/retire_root_mirrors.py`
