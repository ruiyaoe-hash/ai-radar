# AI Radar 时间线例程（给 Alba）

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
写作规范：`CARD_SPEC.md`

## 每次 digest 完成后（08:00 / 13:30 北京时间）

1. **写卡片**  
   按 `CARD_SPEC.md` 产出条目：必有 `date`（YYYY-MM-DD 北京）、`objective`（2–4 条事实）；可选 `judgment` + `judgment_label: "主观判断"`。  
   同步填 `bullets` = `objective`（兼容）。

2. **合并当日归档**  
   - 路径：`public/archive/YYYY-MM-DD.json`（镜像 `data/archive/`）  
   - 按 `url`（或 title+handle）去重后追加/更新当日 `items`  
   - 更新 `public/archive/index.json`：`{ "dates": [ { "date", "count" }, ... ] }`（新在前）

3. **刷新看板窗口 `public/items.json`**  
   - 合并近 **7 个日历日** 的归档（或最多约 **40–50** 张卡）  
   - `items` **最新在前**  
   - 写 `updated`：如 `"2026-10-11 13:30 北京时间"`  
   - 可保留 `window_note` 说明「近期窗口 / 更早见归档」

4. **生成 RSS**  
   ```bash
   python3 generate_feed.py
   ```  
   脚本会：用 objective 写摘要；若有 judgment 则单独标注「主观判断」；并把 `feed.xml` / `items.json` / `archive/*` 镜像到**仓库根目录**（GitHub Pages `path=/`）。

5. **提交并推送**  
   ```bash
   git add public/ index.html items.json feed.xml archive/ generate_feed.py CARD_SPEC.md TIMELINE.md
   git commit -m "chore: AI Radar digest YYYY-MM-DD HH:MM CST"
   git push origin main
   ```

## 目录约定

| 路径 | 用途 |
|------|------|
| `public/items.json` | 看板近期窗口（源） |
| `public/archive/*.json` | 按日全量 |
| `public/archive/index.json` | 归档目录 |
| `public/index.html` / 根 `index.html` | 时间线 UI |
| 根 `items.json` `feed.xml` `archive/` | Pages 发布镜像（由 `generate_feed.py` 同步） |
| `data/` | 可选本地镜像，不必须上 Pages |

## 注意

- 客观与主观**分栏**；旧卡无 judgment 可留空，勿把判断句写进 objective。  
- 不要只覆盖最新一批：归档按日累积，看板是滑动窗口。  
- Pages 从 **main 仓库根目录** 发布；改完跑 `generate_feed.py` 再 push。
