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

`today3.txt` 是纯文本。`feed.xml` 和订阅分册是 RSS 2.0。这两类没有 JSON Schema。

## 2026-10-20

新增 `data/kb.json`（实战图谱），`schema_version` 为 1。同一份内容拆成 `data/tracks.json`、`data/topics.json`、`data/sources.json`、`data/creators.json`。主题页在 `topics/<slug>.html`。这是新文件，没有改已有 feed 的字段名或类型。`practice.json` 仍是第 1 版；每条实操的 id 会在图谱 sources 里出现，并带上 `origin=practice`。

## 2026-10-16

首次公布上表里的公开字段结构。没有废弃字段。

同一天给可能承载改写后站外文本的字段加上 `maxLength`，链接加上 `http` / `https` 格式。没有改名、改类型、删除字段或收紧枚举，所以上表的 `schema_version` 不升。现有公开文件仍能通过这些上限。
