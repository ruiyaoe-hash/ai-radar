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
| `title` | 一句可扫读的事实，像新闻标题。传闻标明「传闻」。不要把参数表塞进标题 |
| `date` | `YYYY-MM-DD`（北京日历日） |
| `time` | `MM-DD HH:MM`（北京） |
| `objective` | 2–4 条客观事实，每条一句完整口语（**不要**再写 `bullets`） |
| `handle` / `url` | 兼容展示的主链；与 `sources[0]` 对齐即可 |

### status 与 P0

- **rumor**：传闻/单源未证实 → 最高只能标 **P0-待证**（UI 单独样式）
- **multi_source**：两独立源
- **confirmed**：一手（primary）或官方确认 → 可升 **正式 P0**
- 升级：**更新原卡** + 可选 `correction`，不新发重复卡

### P0 定义

今天没看到会做错或错过决策。

媒体 alone（单独二手：`role=report` 且没有一手或官方链接）不能升正式 P0，最高是 P0-待证或 P1；机器门闩在 `scripts/annotate_gates.py`（无晋升意图时留 notes，notes 含 `attempt_formal_p0` 才写 `drop_reason=media_alone`），见 `docs/candidate-pool.md`。

### 信息精选的空天

硬门槛不放宽：能按门槛进入信息精选的，仍是正式 P0、多源卡，或同一张卡上两个不同来源。媒体二手不能靠空天规则升成 P0。

某一上海日历日按上面的门槛一条都没有时，不再把这一天留空。用当天最强的一条工具决策或信息简讯顶上，而且只顶一条，不另凑第二条。排序只看对大众访客有没有更清楚的行动：立即行动 / 值得采用，高于可以试用，高于持续观察，高于需要评估，高于暂缓。同一档里，写明了下一步的排前面；还相同就取更新的一条。不因为来自工具就自动压过简讯。

顶上去的卡片仍用访客能读的中文标题、摘要和「所以呢」。`fill_reason`（`empty_day`）和 `promoted_from`（`tool` 或 `brief`）只留在数据里，不写进卡片正文。被顶上的那条简讯不再同时出现在信息简讯。做法页的门槛不动。

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

不要写进公开卡片正文，也不要写进会随 Pages 发布的 `public/owner-actions.json`（该文件是空骨架，`actions` 保持为空）。记在未跟踪的 `owner-actions.local.json`，或私有池 / 飞书：`tried` \| `thesis_updated` \| `shared` \| `ignored`。

## 客观摘要 vs 判断

- objective：只写可核对事实；传闻须归因
- 禁止在 objective 写「我们应该…」「赛道已定」等
- 公开 JSON 只放编辑后的摘要。不要把社交帖原文、`snippet`、`text`、`full_text` 写进归档；那些只留在私有池。单条 `objective` 不超过 schema 里的长度上限。

## 人读层

`id`、`candidate_id`、`status`、`priority`、`sources`、班次和入库时间留在 JSON。给人看的 `title`、`objective`、`so_what.impact`、`so_what.falsifier` 按 [`docs/AIHOT对接与表达规范-v0.md`](docs/AIHOT对接与表达规范-v0.md) 写。私人主报不进公开仓；`DIGEST_LATEST.md` 只是占位。

- 一句一事实，用完整的口语句。不要写「权重能下」这种压缩，写成「模型权重可以下载到自己的电脑或服务器上使用」。
- 英文专名每张卡每种术语最多括注一次。
- 正文不出现 `evt-` / `cand-`，也不写抓取条数。
- 主报顺序是：是什么 → 要点 → 所以呢 → 若证伪。跳过清单放附录，不铺进正文。

决策规则不改。P0 仍是「今天没看到会做错或错过决策」。只有媒体二手不能升正式 P0。写了 `so_what` 就必须有 `falsifier`。

## 从候选池晋升（北京日历日 ≥ 2026-10-15）

遗留卡（2026-10-14 及更早）不要回填。新的 `evt-*`：

| 字段 | 何时写 |
|------|--------|
| `candidate_id` | 对应私有池那一行的 `id`（`cand-YYYYMMDD-` + 12 位十六进制）。公开仓不放池正文 |
| `promotion_path` | `normal`：池里已是 `status_in_pool=promoted`。`emergency`：来不及入池的紧急例外，可以不写 `candidate_id` |

没有 `candidate_id`、也不是 `emergency` 的新卡，校验会失败。能读到池快照时，还要对上 `promoted` 和 `archive_id`。契约见 `docs/candidate-pool.md`。

## 产出后动作

见 `TIMELINE.md`：只追加 `public/archive/` → commit → CI 派生与部署。
