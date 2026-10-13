# AI Radar 卡片写作规范（CARD_SPEC）· schema_version 2

供 Alba 主报 / 晚班例程使用。读者：Rui（AI OPC）与其他从业者。

## 产品焦点（lens）

| lens | 含义 |
|------|------|
| 工具 | 可试用、可接入 agent/workflow |
| 赛道 | 研究路线、资本、模型与行业格局 |
| 模式 | 商业模式、协作范式、交付形态 |
| 时机 | 窗口开/关、收敛与截止日期 |

`tag` 仍写事件类型（发布/论文/评测/观点/工具/行业/…），给人看的主过滤是 **lens**。

## 事件模型（必填）

| 字段 | 要求 |
|------|------|
| `schema_version` | `2` |
| `id` | `evt-YYYYMMDD-slug`（系统生成；RSS guid / 永久链接） |
| `status` | `rumor` \| `multi_source` \| `confirmed` |
| `sources` | `[{url, handle, role}]`，`role`=`primary`\|`analysis`\|`report` |
| `tag` | 事件类型 |
| `lens` | `工具`\|`赛道`\|`模式`\|`时机` |
| `priority` | `P0` 或 `P1` |
| `title` | 可扫读事实标题；传闻标明「传闻」 |
| `date` | `YYYY-MM-DD`（北京日历日） |
| `time` | `MM-DD HH:MM`（北京） |
| `objective` | 2–4 条客观事实（**不要**再写 `bullets`） |
| `handle` / `url` | 兼容展示的主链；与 `sources[0]` 对齐即可 |

### status 与 P0

- **rumor**：传闻/单源未证实 → 最高只能标 **P0-待证**（UI 单独样式）
- **multi_source**：两独立源
- **confirmed**：一手（primary）或官方确认 → 可升 **正式 P0**
- 升级：**更新原卡** + 可选 `correction`，不新发重复卡

### P0 定义

今天没看到会做错或错过决策。

## so_what（可证伪；可选）

```json
"so_what": {
  "lens": "赛道",
  "impact": "...",
  "action": "观察|试用|…",
  "window": "未来 1–2 个季度",
  "confidence": "高|中|低",
  "falsifier": "若…则此判断作废",
  "thesis_id": "T-003"
}
```

**写不出 falsifier 就不要写 so_what。** 长期论点见 `public/theses.json`。

旧字段 `judgment` / `judgment_label` 仍可短暂兼容；新卡优先 `so_what`。

## 工具字段（lens=工具 时建议）

`try_url`, `access`, `integration`, `first_step`, `alternatives`, `tool_radar`（`采纳`\|`试用`\|`评估`\|`暂缓`）

## 班次与首报时差

班次一律写北京时间（Asia/Shanghai）。不要换成美西钟点：11 月 1 日 PDT→PST，与北京的时差从 15 小时变成 16 小时。

| 班次 | `shift` | 时间 | 说明 |
|------|---------|------|------|
| 主报 | `morning` | 08:00 | 每天。覆盖美西上一工作日收盘窗口 |
| 晚班 | `evening` | 21:00 | 周一至周五短报。覆盖中国白天 + 美东早晨 |

- 13:30 `midday` 已取消。历史卡上的 `midday` 留着，不要改归档。
- 05:30 静默班暂缓，直到飞书出站 webhook 可用。它不是发布槽。
- 原 20:00–21:00「只复核、不发新卡」已取消。工作日 21:00 现在会写新卡（见 `config.json`）。
- `shift`：这张卡被编入的下一发布班。
- `lead_lag_hours` / `lead_lag_basis`：按下一发布班假定的时差。`assumed_next_digest` 表示迁移脚本回填。已有值不要覆盖，也不要改历史归档里写好的数。
- `published_at`：信源原发时间，ISO-8601 UTC（`Z`）。用 X `created_at`、RSS `pubDate` 等。信源没有时间就省略，不要用展示字段 `time`（`MM-DD HH:MM`）去猜。
- `ingested_at`：这张卡第一次写入 `public/archive/` 的时间，ISO-8601 UTC。只写一次；按 `id` 更新原卡时不要改。
- 两枚时间都在时，实测首报时差 = `ingested_at` − `published_at`。这和 `lead_lag_hours` 是两套数。
- 旧卡可以没有这两枚时间，校验仍通过。
- 迁移脚本只在字段为空时回填。已经在归档上的卡不会被补 `ingested_at`（那会把迁移时刻当成入库时刻）。

## 主人 action（私用）

不要写进公开卡片正文；记在 `public/owner-actions.json`（或未跟踪的 `owner-actions.local.json`）：`tried` \| `thesis_updated` \| `shared` \| `ignored`。隐私说明见该文件。

## 客观摘要 vs 判断

- objective：只写可核对事实；传闻须归因
- 禁止在 objective 写「我们应该…」「赛道已定」等

## 产出后动作

见 `TIMELINE.md`：只追加 `public/archive/` → commit → CI 派生与部署。
