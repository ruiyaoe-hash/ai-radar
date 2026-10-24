# 快讯层（L2）设计说明

状态：页面和导航已在站上。`public/briefs.json` 里现有条目是 `origin=archive_seed`（摘自已公开归档，不是新事实）。`scripts/derive_briefs.py` 会把打分自动档追加为 `origin=auto_brief`。窗口和条数上限里，自动档每轮最多 20 条；看板窗口仍另说。

## 要解决的问题

主报一周 40 条上下，日均 5–7 张卡。这不是产能不够，是单张卡的成本决定的：一张卡要写 objective 2–4 条、sources、so_what、falsifier，工具卡还要四件套。按这个颗粒度，每班只能出 2–6 张。

结果是两头不讨好：当雷达用，覆盖太窄；当简报用，又不够精。中间缺一层「不值得写判断、但该让人知道」的形态。

## 三层颗粒度

| 层 | 形态 | 成本 | 去向 |
|----|------|------|------|
| L1 卡 | 现在的卡片，带 so_what 和 falsifier | 高 | 主报、看板、feed |
| L2 快讯 | 一条事实 + 一个链接，60–100 字，**不写判断** | 低 | `briefs.html` 单独一页 |
| L3 索引 | 标题 + 来源 + 链接，只列不展开 | 极低 | 周归档附录 |

页面形态先落地。数据现在分两档：`archive_seed` 摘自已公开归档；`auto_brief` 由打分自动档派生。实操不从这里自动上站。

## 数据结构

`public/briefs.json`：

```json
{
  "schema_version": 1,
  "level": "L2",
  "updated": "2026-10-18 18:30 北京时间",
  "items": [
    {
      "id": "brf-20261016-meta-muse-spark-open",
      "level": "L2",
      "date": "2026-10-16",
      "time": "10-16 01:08",
      "title": "一句可扫读的事实",
      "summary": "60–100 字，只写事实，不写判断",
      "url": "https://example.com/a",
      "source": "Meta",
      "lens": "赛道"
    }
  ]
}
```

字段约束：

- `id`：`brf-YYYYMMDD-slug`，和 L1 的 `evt-` 区分开，避免两套 id 混用
- `lens`：沿用现有四个枚举，前端直接复用同一组过滤 chip
- **没有 `so_what`、没有 `priority`、没有 `status`**。L2 不承载判断，所以不需要证伪条件，也不参与 P0 门闩
- 自动档可以多一个可选 `card_copy`。证据固定是「官方原始信息」，动作固定是「持续观察」，`high_priority_review` 固定为 false。短句里没有数字。强制 P0 不投进快讯。五个任务页由另一份改动来排，这里不改 `briefs.html`
- `url` 走现有 `safeHref()` 白名单，渲染时用 DOM API 而不是拼 innerHTML

## 与 L1 的边界

一条信号只能落在一层：URL 已经在公开归档里的，不再进 L2。执行在 `scripts/derive_briefs.py`，不在 `generate_derived.py`（后者继续不读池）。自动档要求高分且有一手；中高分和实操留在私有池审核清单。

## 分三步落地

### 第一步（本 PR）

只加 5 个文件：

- `public/briefs.html`
- `public/assets/briefs.js`
- `public/assets/briefs.css`
- `public/briefs.json`（12 条示例，压自近七天归档，不含新事实）
- `docs/briefs-layer.md`（本文）

零改动现有文件。验证点：CI 的 CSP / beacon / public UI 检查能否容纳第 8 个页面。

**已验证**：本地 `python3 scripts/validate.py` 全绿，`check_csp` 从 7 页变 8 页通过，`check_beacon` 同。新页面不写内联脚本，CSP 里只有 `'self'` 和 Cloudflare beacon，不需要 hash。

### 第二步（打分接通）

- `schemas/briefs.schema.json` 与 `scripts/validate.py` 的 `check_briefs()`
- `scripts/derive_briefs.py` 读私有池里的自动档，写 `public/briefs.json`
- 原文不进公开字段；`safe_http_url`、提示注入校验、`strip_raw_post_fields`
- 做法见 `docs/score-and-briefs.md`

### 第三步（展示）

导航已经改成任务名。顶栏由 `public/assets/shell.js` 写出五个入口：信息精选（`today.html`）、信息简讯（`briefs.html`，`data-page="briefs"`）、工具决策、实战手册、专题观察。订阅更新在右侧。`week.html` 跳到 `briefs.html#archive`。次要入口（博主库、做法条目、随笔、飞书订阅群、给 Agent 用、收录标准、这是什么、反馈）收在「更多」。`scripts/validate.py` 的 `check_public_ui` 锁住这个顺序。信息精选和信息简讯不互相收录。

窗口和看板切换仍单独做：

- `generate_derived.py` 的 `MAX_ITEMS=50` / `WINDOW_DAYS=7` 调整
- 看板加「今日 / 本周」切换

**为什么窗口调整另开**：`MAX_ITEMS` 和 `WINDOW_DAYS` 是三个常量，改起来三行，但窗口该多大取决于 L2 落地后的总条目数。现在拍一个数，等 L2 定型还得再改一次，而且改完会立刻改变你现有看板的观感。先定结构，再调参数。

## 回滚

页面本身仍是那 5 个文件。导航入口在 `public/assets/shell.js`，对应检查在 `scripts/validate.py`。要撤掉入口，删掉「快讯」那一行，并去掉 `check_public_ui` 里对「快讯」的检查。只删页面、不改导航，侧栏会指向不存在的地址。Pages 部署只上传 `public/`。

## 风险

1. **L2 会稀释注意力**。12 条快讯的阅读成本低于 6 张卡，但 40 条就不是了。建议设上限：每班 L2 不超过 20 条，超了按 `source_tier` 和 `lens` 截断。
2. **示例数据被当真**。页面底部已标注「本页当前为示例数据」，第二步接真实数据时必须删掉这句。
3. **两套 id 并存**。`brf-` 和 `evt-` 混用时，检索和去重要各自处理。第一步先在文档里把边界写死，第二步再用校验兜住。

## 验收标准

- 合并后 `items.json`、`feed.xml`、`today3.txt` 与合并前逐字节一致
- `briefs.html` 在 1280px 和 375px 下都不横向滚动
- 快讯条目渲染不产生任何内联脚本，CSP 不放松
- 第二步接入真实数据后，L2 覆盖率 ≥ 候选池 active 行的 60%
