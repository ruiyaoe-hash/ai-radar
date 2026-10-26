# 公开字段变更记录

给人看的说明在 [给 Agent 用](https://ruiyaoe-hash.github.io/ai-radar/agent.html)。这里记字段形状怎么变。

## 规则

- 文件里如果有 `schema_version`（整数），只有不兼容变更才加 1：改名、改类型、删除字段、收紧枚举。只增加可选字段不升版本。
- 标成废弃的字段至少再保留 90 天，并且留在当前 `schema_version` 里。删除只发生在升版本之后。
- `tools-radar.json` 和 `archive/index.json` 没有 `schema_version`。不兼容的形状变化同样先写在这里；废弃字段同样至少保留 90 天。

## 当前版本

| 文件 | schema_version | 字段结构 |
| --- | --- | --- |
| `items.json` 与其中的卡片 | 2 | [items.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/items.schema.json)、[card.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/card.schema.json) |
| `archive/YYYY-MM-DD.json` | 2 | [archive-day.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/archive-day.schema.json) |
| `practice.json` | 1 | [practice.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/practice.schema.json) |
| `data/kb.json` | 1 | [atlas.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/atlas.schema.json) |
| `theses.json` | 1 | [theses.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/theses.schema.json) |
| `tools-radar.json` | （无） | [tools-radar.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/tools-radar.schema.json) |
| `archive/index.json` | （无） | [archive-index.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/archive-index.schema.json) |
| `briefs.json` | 1 | [briefs.schema.json](https://ruiyaoe-hash.github.io/ai-radar/schemas/briefs.schema.json) |

`today3.txt` 是纯文本。`feed.xml` 和订阅分册是 RSS 2.0。这两类没有 JSON Schema。

## 2026-10-26

`picks.json` 的条目可以多两个机器字段：`fill_reason`（`empty_day`）和 `promoted_from`（`tool` 或 `brief`）。这份列表没有 schema_version，也不升任何版本：只增加可选字段，页面不展示这两个词。硬门槛仍是 P0、多源，或同一张卡上两个不同来源。某一上海日按硬门槛没有精选时，用当天最强的一条工具或简讯顶上，只一条，优先级不改成 P0。

## 2026-10-24

`briefs.json` 增加可选字段 `why` 和 `summary` 的字数上限放到 240。`schema_version` 仍是 1：没有改名、改类型或删除字段。`why` 是「为什么值得看」，`affect` 是「对我有什么影响」。两条都是写给访客的中文，不写编辑流程。

`picks.json` 是信息精选的按天列表，由归档派生，没有单独的 schema_version。`data/watch.json` 是专题观察里跨天的领域进展，同样是可选的公开列表。

## 2026-10-23

`data/kb.json` 的 `topics` 允许空数组。`schema_version` 仍是 1：没有改名、改类型或删除字段，只放宽最少条数，让公开站在没有主题时仍合法。五个方向 `tracks` 仍至少 5 条。

## 2026-10-22

卡片和快讯增加可选对象 `card_copy`。`schema_version` 不变：卡片仍是 2，快讯仍是 1。没有改名、改类型或删除已有字段。已经公开的 JSON 不带这个对象，仍然合法。页面不在这次改。

四个字段都是给卡片扫读的，不是算法分数：

- `watch_reason`：为什么值得看。短句，不允许数字。
- `evidence_label`：`官方原始信息`、`多源确认`、`尚待核实`。
- `suggested_action`：`立即行动`、`持续观察`、`暂缓`。默认动作叫「立即行动」，升级、打补丁、试用工具都用这一句。同一天草稿里曾写成「立即试用」，公开 JSON 没有用过那个值，卡片 `schema_version` 仍是 2。
- `high_priority_review`：要优先审。不是归档卡上的 `priority`（P0 / P1），也不是自动发布。

快讯上收窄：证据只能是 `官方原始信息`，动作只能是 `持续观察`，`high_priority_review` 必须是 false。自动档不把强制 P0 投进来。

## 2026-10-21

`briefs.json` 补上公开 schema，`schema_version` 仍是 1。条目增加可选字段 `origin`（`archive_seed` 或 `auto_brief`）和 `candidate_id`（只在自动档上必填）。没有改名、改类型或删除已有字段。

同一天 `data/kb.json` 仍是第 1 版。新增可选字段：`demand_refreshed_at`、`demand_refreshed_at_utc`、`demand_formula`；主题上的 `demand_samples`、`demand_refreshed_at`、`unverified_practice`、`verified_practice`；来源上的 `verified`、`demand_from`、`demand_observed_at`。`save_ratio` 改为平滑收藏比，类型仍是数。没有改名或删除。

新文件 `data/demand.json`（需求信号滚动）和 `data/topic-suggestions.json`（实操主题建议），`schema_version` 都是 1。字段说明见 `demand.schema.json`、`topic-suggestions.schema.json`。

## 2026-10-20

新增 `data/kb.json`（实战图谱），`schema_version` 为 1。同一份内容拆成 `data/tracks.json`、`data/topics.json`、`data/sources.json`、`data/creators.json`。主题页在 `topics/<slug>.html`。这是新文件，没有改已有 feed 的字段名或类型。`practice.json` 仍是第 1 版；每条实操的 id 会在图谱 sources 里出现，并带上 `origin=practice`。

## 2026-10-16

首次公布上表里的公开字段结构。没有废弃字段。

同一天给可能承载改写后站外文本的字段加上 `maxLength`，链接加上 `http` / `https` 格式。没有改名、改类型、删除字段或收紧枚举，所以上表的 `schema_version` 不升。现有公开文件仍能通过这些上限。
