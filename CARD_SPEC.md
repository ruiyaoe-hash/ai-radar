# AI Radar 卡片写作规范（CARD_SPEC）· schema_version 2

供 Alba 早报 / 主报例程使用。读者：Rui（AI OPC）与其他从业者。

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

- 发布班次（北京时间）：08:00 `morning`、13:30 `midday`
- 验证班次：20:00–21:00 只复核、不发新卡（见 `config.json` 的 `evening_verify`）
- `shift`：这张卡被编入的下一发布班
- `lead_lag_hours`：信源时间到下一发布班的小时数
- `lead_lag_basis`：`assumed_next_digest` 表示按班次假定回填。Alba 有实测首报时差时覆盖 `lead_lag_hours`，不要改历史归档里已写好的值
- 迁移脚本只在字段为空时回填，不覆盖手写值

## 主人 action（私用）

不要写进公开卡片正文；记在 `public/owner-actions.json`（或未跟踪的 `owner-actions.local.json`）：`tried` \| `thesis_updated` \| `shared` \| `ignored`。隐私说明见该文件。

## 客观摘要 vs 判断

- objective：只写可核对事实；传闻须归因
- 禁止在 objective 写「我们应该…」「赛道已定」等

## 产出后动作

见 `TIMELINE.md`：只追加 `public/archive/` → commit → CI 派生与部署。
