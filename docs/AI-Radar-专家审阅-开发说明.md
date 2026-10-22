# AI Radar · 专家审阅与开发说明

> 版本说明：基于仓库 `ruiyaoe-hash/ai-radar`（截至 2026-10-11 北京时间）与运行中的 GitHub Pages / Grok Bot Alba 例程实况整理。  
> 本文供外部 AI / 产品 / 工程专家做深度评审；语气偏工程说明，非产品宣传稿。

---

## 1. 文档目的与读者

### 1.1 目的

帮助**从未参与过内部对话**的评审者在一小时内搞清：

1. AI Radar 解决什么问题、核心价值主张是什么；
2. 端到端如何运转（信源 → 卡片 → 归档/看板/RSS → 人与 Agent）；
3. 当前技术选型与数据模型是否合理；
4. 哪里已经做成、哪里是债、下一步该押什么。

### 1.2 读者

| 角色 | 期望收获 |
|------|----------|
| AI 产品 / OPC 同行 | 是否值得对标；客观/主观分栏是否可复用 |
| 前端 / 静态站工程师 | Pages + JSON 时间线是否够用；演进路径 |
| Agent / 自动化工程师 | 例程编排、水位、RSS 是否可被 Agent 稳定消费 |
| 内容 / 情报编辑 | CARD_SPEC 是否可执行、P0 标准是否清晰 |

### 1.3 不在本文范围

- 具体 X 帖文内容的真伪核验（由每日 digest 承担）
- 飞书桥接实现细节、Grok Bot 内部调度源码
- 商业化定价与法务意见

---

## 2. 一句话定位与核心价值主张

**一句话：**  
AI Radar 是面向 AI OPC / 从业者的**按日归档情报时间线**：从精选 X（Twitter）A 级信源拉取信号，写成「客观摘要 + 可选主观判断」卡片，经静态看板与 RSS 分发，供人扫读与 Agent 订阅。

**核心价值主张（可证伪）：**

| 主张 | 落地形态 |
|------|----------|
| 只盯高信噪一手密度，不刷全网 | `config.json` 中约 30 个 A 级 handle；B 级不进默认实时 |
| 事实与判断分栏，防误导 | `objective` / `judgment` 字段；UI 琥珀色「主观判断」标记；RSS 同样分栏 |
| 可追溯、可分享、零登录 | GitHub Pages 公开静态站 + 原文链到 X |
| 人读 + Agent 读同一数据源 | `items.json` / 按日 `archive/` + `feed.xml` |
| 节奏可预期 | 北京时间每天 08:00 主报 + 工作日 21:00 晚班（Grok Bot Alba 例程；不写美西钟点） |

**刻意不做的事：** 秒级推送、全量爬取、服务端搜索、付费 X Streaming API、微信机器人。

---

## 3. 目标用户与使用场景

### 3.1 产品所有者：项目所有者

| 维度 | 说明 |
|------|------|
| 决策场景 | 工具选型、赛道/并购信号、商业模式与「时机感」 |
| 阅读节奏 | 08:00 主报扫 P0；工作日 21:00 晚班补中国白天与美东早晨；周末只有主报 |
| 分发偏好 | 看板链接可转微信/飞书；P0 可选飞书 DM（见 §10） |
| 质量红线 | 客观栏禁止「应该 All-in」类判断；传闻必须标明 |

### 3.2 广义 AI 创业者 / 从业者

- 通勤刷时间线：按标签芯片（发布 / 论文 / 工具…）或「仅 P0」过滤；
- 回溯某日：归档下拉加载 `archive/YYYY-MM-DD.json`；
- 分享：复制 Pages URL，接收方无需登录。

### 3.3 Agent / 阅读器订阅

- RSS：`feed.xml`（标题含 `[P0/tag]`，description 分「客观摘要」与「【主观判断】」）；
- 结构化 JSON：`items.json`（近窗）+ `archive/*.json`（全量按日）；
- 水位：`state.json` 中 `watermark` / `seen_ids`（运行态，通常不上 Pages 消费路径）。

---

## 4. 产品能力现状

### 4.1 看板时间线（已实现）

- 单页深色 UI：`index.html`（约 290 行，无框架）
- 数据：`fetch('./items.json?' + Date.now())` 防 CDN 脏缓存
- 按 `date` 分组 + sticky 日头；P0 左色条红色
- 说明文案明确：近窗约 7 天 / 最多约 50 条；更早见归档

### 4.2 按日归档（已实现）

- `archive/YYYY-MM-DD.json`：`{ date, count, items[] }`
- `archive/index.json`：`{ dates: [{ date, count }, ...] }`（新在前）
- UI：`<select>` 切换「看板」与各归档日

### 4.3 RSS（已实现）

- `generate_feed.py` 从 `public/items.json` 生成 RSS 2.0 + Atom self-link
- 同步镜像到仓库根（Pages `path=/`）

### 4.4 过滤（已实现）

芯片：全部 / 发布 / 论文 / 评测 / 观点 / 工具 / 行业 / 仅 P0。  
注：卡片 tag 枚举实际更宽（并购、案例、产品、模型、安全等），部分 tag 无对应芯片，只能靠「全部」看到。

### 4.5 客观 / 主观分区（已实现 · 内容侧待充实）

- Schema 与 UI/RSS 渲染均已支持 `judgment`
- 截至 2026-10-11 样本卡：`judgment` 多为空数组（规范允许「无可靠判断则省略」；但产品差异化尚未充分体现）

### 4.6 例行 digest（已实现）

| 班次 | 北京时间 | 产出 |
|------|----------|------|
| 主报 | 08:00，每天 | 卡片 + 飞书/私有池里的主报。公开仓的 `DIGEST_LATEST.md` 只是占位，不放私人选型。覆盖美西上一工作日收盘窗口 |
| 晚班 | 21:00，周一至周五 | 短报。覆盖中国白天 + 美东早晨 |
| （已取消） | 13:30 | 不再作为主报 |
| （暂缓） | 05:30 | 静默班，直到飞书出站 webhook 可用 |

钟点存 **Asia/Shanghai**。不要写成美西钟点：11 月 1 日 PDT→PST，时差从 15 小时变成 16 小时。

由 Grok Bot **Alba** 例程驱动（非仓库内 cron）。

---

## 5. 内容标准（CARD_SPEC）

规范文件：仓库根 `CARD_SPEC.md`。

### 5.1 选题优先级

1. **新工具**（可试用、可接入 agent/workflow）
2. **新方向 / 新赛道**（研究路线、产品形态、资本与并购）
3. **新商业模式**（定价、分发、平台、infra 变现）
4. **时机感**（窗口开/关）

次要：八卦、无信息量短评、口径不清的二手转述。

### 5.2 P0 / P1

| 级 | 含义 | 典型触发 |
|----|------|----------|
| P0 | 必看 | 新模型/权重、官方重大发布、并购/加码硬信号、重大评测登顶、安全事件 |
| P1 | 高价值 | 论文首发、深度技术线、硬核实测、产品形态演进 |

早期呈现方案文档中还有 P2（噪声丢弃）；当前看板不展示 P2。

### 5.3 客观 vs 主观

| 栏 | 规则 |
|----|------|
| `objective`（必填 2–4 条） | 可核对事实：谁宣布了什么、数字、时间表、开源范围、基准、资金口径；传闻须归因 |
| `judgment`（可选 1–3 条） | 趋势 / 赛道 / 模式 / 时机；须有 `judgment_label: "主观判断"`；禁止伪装成新闻 |
| `bullets` | 与 `objective` 同步（兼容旧看板） |

### 5.4 反误导规则（摘要）

- 禁止客观栏出现「我们应该…」「赛道已定」「显然是下一波红利」
- 禁止把观点作者的推断写成板上钉钉
- 标题中传闻须标明「传闻」
- 无可靠判断时：**省略或空数组**，不要硬写

### 5.5 信源分层（清单侧）

详见 `/workspace/AI-X信源清单-监控版.md`：

| 层 | 规模 | 用途 |
|----|------|------|
| A 级 | ~22–30 | 默认监控；写入 `config.json` `a_tier` |
| B 级 | ~15–18 | 日报/摘要即可，不进即时 |
| C 级 | 观察/降噪 | 不进默认监控（重复官号、娱乐向等） |

筛选原则：**一手发布 > 论文/评测雷达 > 高质量拆解**；砍营销号、复读向、弱相关 AIGC。

---

## 6. 端到端架构

2026-10-22 起，强制 P0（Forced P0，必须先给人看的通道）以 `scripts/force_p0.py` 为准，例程只是再看一眼。它把行送进审核队列，不自动写公开归档或今日必看。打分的生产档仍是 v1；v2 先影子记录。同一行可以带 `card_copy`：为什么值得看、证据标签、建议动作，以及优先审标记。这些是给卡片看的字，不暴露分数。五个任务页（今日重点 / 最新动态 / 工具决策 / 实战手册 / 专题观察）由另一份改动来排。说明在 [`score-and-briefs.md`](./score-and-briefs.md)，对照回测在 [`score-ab-backtest.md`](./score-ab-backtest.md)。标注的主路径是聊天里对每条选 A 或 B，回执再汇总；多列表只作批量导出。下面的图仍是给人看的总览，班次和 Pages 没有改。



```
┌─────────────────────────────────────────────────────────────────┐
│  A 级 X 账号（config.a_tier）                                      │
│       │ 公开读取（Grok Bot X MCP / 额度 ~30/min · ~1000/day）        │
│       ▼                                                           │
│  state.json（watermark + seen_ids 去重）                           │
│       │                                                           │
│       ▼                                                           │
│  Alba 例程（08:00 主报 / 工作日 21:00 晚班，北京时间）               │
│  · 分级 P0/P1 · 按 CARD_SPEC 写卡片                                  │
│  · 合并 public/archive/YYYY-MM-DD.json                              │
│  · 刷新 public/items.json（近 7 日 / ≤~50 卡）                       │
│       │                                                           │
│       ▼                                                           │
│  python3 generate_feed.py                                         │
│  · feed.xml（客观/主观分栏）                                         │
│  · 镜像 items.json / archive/* / feed.xml → 仓库根                   │
│       │                                                           │
│       ▼                                                           │
│  git commit + git push origin main（gh / 凭据在 box）               │
│       │                                                           │
│       ▼                                                           │
│  GitHub Pages（branch main · path=/）                               │
│  https://ruiyaoe-hash.github.io/ai-radar/                          │
│       │                                                           │
│       ├── 人：浏览器看板 / 归档选择 / 标签过滤                         │
│       ├── 阅读器 / Agent：feed.xml · items.json · archive/*.json    │
│       └── 可选：飞书 P0 DM（Alba 桥 · 仅 reply pending message_id）   │
└─────────────────────────────────────────────────────────────────┘
```

### 6.1 与早期「呈现方案」的对照

早期文档（`AI-X监控呈现方案.md`）设想三层：飞书即时 + 滚动看板 + 日报，轮询 15–30 分钟。  
**现状落地偏「方案 α 的瘦身版」：**

| 设想 | 现状 |
|------|------|
| 15–30 分钟近实时轮询 | 改为固定两班 digest（额度与人读节奏更匹配） |
| 飞书 P0 即时 | 桥可用但多为 reply-only；pending=0 时无主动私信路径 |
| GitHub Pages 看板 | **已实现**，且升级为按日归档 + 客观/主观分栏 |
| 微信机器人 | 明确不做；靠链接分享 |

---

## 7. 技术栈与仓库结构

### 7.1 技术栈

| 层 | 选型 | 备注 |
|----|------|------|
| 前端 | 原生 HTML + CSS + JS | 无构建、无框架、无 npm |
| 数据 | JSON 文件 | 看板窗口 + 按日归档 |
| RSS | Python 3 脚本 `generate_feed.py` | stdlib only |
| 托管 | GitHub Pages | `main` 根目录；`.nojekyll` 保证 `feed.xml` 不被 Jekyll 吃掉 |
| 发布 | `gh` / `git push` as `ruiyaoe-hash` | 在共享 box 上执行 |
| 编排 | Grok Bot Alba routines | 非仓库内 Actions（当前） |
| 信源 API | X 公开读取（MCP） | 非付费 Streaming |
| 可选推送 | 飞书桥（Alba） | 边界见 §10 |

### 7.2 仓库结构（逻辑）

```
ai-radar/
├── README.md                 # 入口：看板/RSS/规范链接
├── CARD_SPEC.md              # 卡片写作规范
├── TIMELINE.md               # 例程步骤（给 Alba）
├── config.json               # timezone · digests · a_tier
├── state.json                # watermark · last_run · seen_ids（运行态）
├── DIGEST_LATEST.md          # 公开占位。私人主报不进本仓正文
├── SAMPLE_DIGEST.md          # 样例早报
├── generate_feed.py          # RSS + 根目录镜像
├── .nojekyll
├── public/                   # ★ 站点源（权威）
│   ├── index.html
│   ├── items.json
│   ├── feed.xml
│   ├── README.md
│   └── archive/
│       ├── index.json
│       ├── YYYY-MM-DD.json
│       └── ...
├── index.html / items.json / feed.xml / archive/   # Pages 镜像（脚本同步）
├── data/                     # 可选本地镜像，不必须上 Pages
└── docs/                     # 文档（本审阅说明等）
```

**重要约定：** `public/` 为源；Pages 读的是**仓库根**。忘记跑 `generate_feed.py` 会导致根与 `public/` 漂移。

### 7.3 仓库元数据（GitHub）

| 项 | 值 |
|----|-----|
| Repo | https://github.com/ruiyaoe-hash/ai-radar |
| Visibility | public |
| Default branch | `main` |
| Pages | enabled（`has_pages: true`） |
| Created | 2026-10-09（UTC） |
| Primary language | HTML |
| License | 无 |

---

## 8. 数据模型

### 8.1 `items.json`（看板窗口）

```json
{
  "updated": "2026-10-11 08:11 北京时间",
  "window_note": "看板展示近几日精选（约 7 天 / 最多约 50 条）；更早日期见归档。",
  "items": [ /* Card */ ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `updated` | string | 人类可读北京时间戳 |
| `window_note` | string | 可选；解释滑动窗口 |
| `items` | Card[] | **最新在前** |

### 8.2 Card

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `tag` | ✓ | string | 发布/论文/评测/观点/工具/行业/产品/并购/案例/安全/模型… |
| `priority` | ✓ | `"P0"` \| `"P1"` | |
| `title` | ✓ | string | 可扫读事实标题；传闻标「传闻」 |
| `handle` | ✓ | string | 不含 `@` |
| `time` | ✓ | string | `MM-DD HH:MM`（北京） |
| `date` | ✓ | string | `YYYY-MM-DD`（北京日历日） |
| `url` | ✓ | string | 原文 X 链接；亦作去重键 |
| `objective` | ✓ | string[2–4] | 客观摘要 |
| `bullets` | ✓ | string[] | 与 objective 同步（兼容） |
| `judgment` | | string[0–3] | 主观判断；可 `[]` |
| `judgment_label` | 有 judgment 时 | `"主观判断"` | 固定文案 |

### 8.3 `archive/YYYY-MM-DD.json`

```json
{
  "date": "2026-10-11",
  "count": 3,
  "items": [ /* Card */ ]
}
```

### 8.4 `archive/index.json`

```json
{
  "dates": [
    { "date": "2026-10-11", "count": 3 },
    { "date": "2026-10-10", "count": 4 }
  ]
}
```

### 8.5 `state.json`（运行水位）

| 字段 | 说明 |
|------|------|
| `watermark` | ISO 时间（UTC Z）；拉取下界 |
| `last_run` | 上次例程完成时间（UTC Z） |
| `seen_ids` | X status id 字符串列表，去重 |

注意：水位时间戳为 **UTC**；卡片展示时间为 **北京**。评审时勿混读。

### 8.6 `config.json`

```json
{
  "timezone": "Asia/Shanghai",
  "digests": ["08:00", "21:00"],
  "a_tier": [ "karpathy", "gdb", /* …约 30 个 */ ]
}
```

### 8.7 RSS 字段映射

| RSS | 来源 |
|-----|------|
| `title` | `[priority/tag] title` |
| `link` / `guid` | `url`（permalink） |
| `pubDate` | 卡上有 `published_at` 时用它（UTC）；否则由 `date` + `time` 解析为 +0800 |
| `description` | HTML：客观摘要列表 + 可选【主观判断】+ 来源/日期 |

---

## 9. 运行与发布流程

规范文件：`TIMELINE.md`。

### 9.1 每次 digest 完成后（08:00 主报 / 工作日 21:00 晚班，北京时间）

1. **写卡片** — 按 CARD_SPEC；`bullets = objective`
2. **合并当日归档** — `public/archive/YYYY-MM-DD.json`；按 `url`（或 title+handle）去重；更新 `archive/index.json`
3. **刷新看板窗口** — 合并近 7 个日历日（或最多约 40–50 卡）→ `public/items.json`；写 `updated`
4. **生成 RSS + 镜像** — `python3 generate_feed.py`
5. **提交推送**
   ```bash
   git add public/ index.html items.json feed.xml archive/ generate_feed.py CARD_SPEC.md TIMELINE.md
   git commit -m "chore: AI Radar digest YYYY-MM-DD HH:MM CST"
   git push origin main
   ```

### 9.2 CDN / 缓存注意

- 前端对 JSON 使用 `?` + `Date.now()` query bust，降低 Pages CDN 陈旧风险；
- HTML 本身仍可能被缓存；大改 UI 后若用户看到旧壳，需硬刷新或等 CDN TTL；
- 根目录与 `public/` 必须成对更新，否则出现「RSS 新、看板旧」类漂移。

### 9.3 历史教训（已部分修复）

早期曾出现**覆盖式**更新（只保留最新一批、冲掉历史）。现规范明确：**归档按日累积，看板是滑动窗口**。评审时应抽查 `archive/` 是否随日增长、而非被单文件覆盖。

---

## 10. 安全与边界

| 主题 | 现状与风险 |
|------|------------|
| 公开 Pages | 无密钥、无登录；内容来自公开 X，默认可读 |
| 仓库凭据 | `git` / `gh` 凭据在共享 **box**；勿写入 Pages 可下载路径 |
| `state.json` | 含水位与帖 id，无 API key；是否提交仓库属运维选择 |
| X 限额 | ~30/min、~1000/day；两班 digest + 突发补拉需留余量；不可按「每账号每分钟」扩展 |
| 飞书 | 仅能 **reply** 已有 pending `message_id`；不可把桥当成任意主动广播通道 |
| 内容风险 | 二手传闻、估值口径、合规敏感工具（如逆向 MCP）——卡片应归因与免责，不给违法操作步骤 |
| 供应链 | 无 npm；攻击面主要是 GitHub 账号与 box 凭据 |

---

## 11. 已知局限与技术债

诚实清单（按严重度大致排序）：

1. **主观判断栏长期为空** — Schema/UI 就绪，内容未形成稳定产出；差异化未兑现。
2. **无服务端** — 无全文检索、无用户账户、无个性化推送、无服务端去重 API。
3. **信源偏 X** — 无官网 blog / GitHub Release / Discord / 新闻社双源校验；X 删帖后链接失效。
4. **例程在 Bot 侧** — 仓库内无 GitHub Actions 备份；Alba/例程故障时无自动降级流水线。
5. **三份数据副本** — `public/`、根镜像、`data/`；人为同步成本，易漂移。
6. **标签芯片与 tag 枚举不一致** — 并购/案例/产品/模型等无芯片入口。
7. **归档历史很短** — 公开可见自 2026-10-10 起；更早样例在 `SAMPLE_DIGEST.md`，未回填 archive。
8. **无 schema 校验** — 缺 JSON Schema / CI 校验，坏卡可上线。
9. **无自动化测试** — `generate_feed.py`、前端渲染均靠人工眼看。
10. **去重键弱** — 主要靠 `url` / `seen_ids`；同一事件多账号报道仍可能多卡（规范希望「一手 + 一条最佳中文拆解」，执行靠人/模型自觉）。
11. **P0 飞书通道不稳定** — 依赖 pending；digest 备注中常见「P0 仅本聊天」。
12. **无 License / 无 CONTRIBUTING** — 对外协作与二次分发边界不清。
13. **handle 变更** — 如 LMSYS→arena；配置需人工追。
14. **周末薄报** — 官号/研究大 V 原创少时，质量靠「敢 drop」而非「凑条数」——这是优点，但读者需理解波动。

---

## 12. 演进路线建议

标注：**已实现** / **建议**。

### 12.1 内容质量

| 项 | 状态 | 说明 |
|----|------|------|
| A 级白名单 + 砍噪声原则 | 已实现 | 清单 + config |
| 客观/主观分栏规范 | 已实现 | CARD_SPEC |
| 每卡强制或抽样写 judgment | **建议** | 否则分栏是空壳；可对 P0 强制 1 条 |
| 同一事件「一手 + 中文拆解」去重策略脚本化 | **建议** | 降低多卡刷屏 |
| 引入第二信源（官网/Release）交叉验证 P0 | **建议** | 降传闻风险 |
| 编辑评分 / 事后纠错字段 | **建议** | `correction` 或划线更新 |

### 12.2 产品形态

| 项 | 状态 | 说明 |
|----|------|------|
| 静态时间线 + 归档 + RSS | 已实现 | |
| 标签芯片补齐（并购/模型/产品/案例…） | **建议** | 与 CARD_SPEC 枚举对齐 |
| 「今日 5 条速览」纯文本块 | **建议** | 方便复制到微信群 |
| 周报自动汇总页 | **建议** | 从 archive 聚合 |
| 轻量搜索（客户端 fuse.js 扫近窗） | **建议** | 仍免服务端 |
| 深色/浅色切换 | **建议** | 呈现方案有提，未做 |

### 12.3 工程可靠性

| 项 | 状态 | 说明 |
|----|------|------|
| generate_feed 镜像根目录 | 已实现 | |
| `.nojekyll` | 已实现 | |
| JSON Schema + CI 校验 | **建议** | PR/push 阻断坏卡 |
| GitHub Action 定时兜底（Bot 故障时） | **建议** | 至少能重跑 feed 或告警 |
| 单一数据根，消灭 `data/` 与根镜像歧义 | **建议** | 或文档强制「只写 public」 |
| 监控 Pages 部署失败 / 空 items | **建议** | |
| 归档回填与保留策略（如 90 天） | **建议** | |

### 12.4 分发与商业

| 项 | 状态 | 说明 |
|----|------|------|
| 公开 Pages + RSS | 已实现 | |
| 飞书 P0 可靠主动推送 | **建议** | 需产品层重新设计桥权限或 webhook |
| 邮件/周刊 | **建议** | 非实时人群 |
| 付费深度版（OPC 决策备忘） | **建议** | 主观判断栏可做成付费差异化；需先把内容做稳 |
| License（如 CC BY-NC / MIT 文档 + 数据说明） | **建议** | |

---

## 13. 专家评审问题清单

便于挑刺（请直接打分或给反例）：

1. **价值主张**：与「手动刷 List / 付费 Newsletter / 自建 Notion」相比，Radar 的不可替代点是否只剩「客观/主观分栏 + Agent RSS」？若判断栏长期为空，护城河还在吗？
2. **信源策略**：A 级 ~30 是否过宽或过窄？中文拆解（宝玉/邵猛/东锡）权重是否过高，导致「二手叙事」主导看板？
3. **P0 标准**：并购「传闻」标 P0 是否合适？是否应强制「双源确认」才进 P0？
4. **节奏**：每天 08:00 主报 + 工作日 21:00 晚班是否盖住美西收盘与美东早晨？13:30 已取消。排班是否仍被写成美西钟点（DST 会漂）？
5. **数据模型**：`bullets` 与 `objective` 双写是否该废弃其一？Card 是否缺稳定 `id`（非 url）？
6. **归档正确性**：是否仍存在覆盖写风险？如何证明 10-10 的 4 条不会被下次 digest 冲掉？
7. **三副本问题**：`public/` / 根 / `data/` 长期如何治理？
8. **前端**：无构建单页在 50 卡时是否够用？归档按日全量加载是否应做分页/虚拟列表？
9. **RSS**：`guid` 用 X url，删帖后永久失效如何处理？是否需要自有 permalink？
10. **安全**：公开站聚合逆向/安全类工具信息时，免责声明是否足够？
11. **自动化**：例程全在 Alba，仓库无 Actions——单点故障可接受吗？
12. **飞书**：reply-only 是否应降级为「明确不做即时推送」，避免用户心智落差？
13. **可测试性**：最小 CI 应该测什么三件事？
14. **商业化**：若面向广义创业者收费，最小可售卖单元是什么（周报？判断栏？私有 List）？
15. **度量**：目前无打开率/RSS 订阅数/卡片点击——下一阶段该埋哪些**隐私友好**指标？

---

## 14. 附录

### 14.1 关键 URL

| 用途 | URL |
|------|-----|
| 看板 | https://ruiyaoe-hash.github.io/ai-radar/ |
| RSS | https://ruiyaoe-hash.github.io/ai-radar/feed.xml |
| 仓库 | https://github.com/ruiyaoe-hash/ai-radar |
| 近窗 JSON | https://ruiyaoe-hash.github.io/ai-radar/items.json |
| 归档索引 | https://ruiyaoe-hash.github.io/ai-radar/archive/index.json |
| 示例日归档 | https://ruiyaoe-hash.github.io/ai-radar/archive/2026-10-11.json |

### 14.2 相关本地文档（box）

| 路径 | 内容 |
|------|------|
| `/workspace/ai-radar/` | 主仓库工作副本 |
| `/workspace/AI-X信源清单-监控版.md` | A/B/C 级信源与筛选逻辑 |
| `/workspace/AI-X监控呈现方案.md` | 早期免费监控与呈现方案（架构对照用） |
| `/workspace/AI-Radar-专家审阅-开发说明.md` | 本文 |
| `/workspace/ai-radar/docs/AI-Radar-专家审阅-开发说明.md` | 本文仓库内副本 |

### 14.3 目录树摘要（不含 `.git`）

```
.ai-radar/
  CARD_SPEC.md  TIMELINE.md  README.md  config.json  state.json
  generate_feed.py  DIGEST_LATEST.md  SAMPLE_DIGEST.md  .nojekyll
  public/{index.html, items.json, feed.xml, archive/*}
  index.html  items.json  feed.xml  archive/*   # Pages 镜像
  data/{items.json, archive/*}                  # 可选本地镜像
  docs/AI-Radar-专家审阅-开发说明.md
```

### 14.4 示例 Card（节选，来自 2026-10-11 归档）

```json
{
  "tag": "并购",
  "priority": "P0",
  "title": "传闻：英伟达洽谈收购或加码 Reflection AI（Beam 刚火）",
  "handle": "dongxi_nlp",
  "time": "10-11 06:51",
  "url": "https://x.com/dongxi_nlp/status/2109054116458566094",
  "date": "2026-10-11",
  "objective": [
    "东锡梳理：Beam 被视为西方开源模型重要突破后不久，传出 NVIDIA 收购 Reflection 的消息",
    "外媒/早报口径多为「洽谈收购或追加投资」；3 月估值约 $250 亿；英伟达已投约 $8 亿",
    "同脉络支出：Essential AI / Poolside / Reflection；分发 Hugging Face；infra Nexusflow / Groq——不止卖卡"
  ],
  "bullets": [ "…与 objective 相同…" ],
  "judgment": [],
  "judgment_label": "主观判断"
}
```

### 14.5 运维上下文速查

| 项 | 值 |
|----|-----|
| 例程 | Alba · 北京 08:00 主报（每天）+ 21:00 晚班（周一至周五）。13:30 已取消 |
| 发布身份 | `ruiyaoe-hash` → GitHub Pages `main` `/` |
| X 额度 | ~30/min · ~1000/day（公开读） |
| 飞书 | 可选；仅 reply pending |
| 产品主人 | 项目所有者 |

---

*文档结束。评审反馈请直接对照 §13 问题清单逐条回复，并尽量附「应改成什么样」的反例或补丁级建议。*
