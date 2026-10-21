# 撤稿与暂停班次

给睿和 Alba。公开页不能热改仓库。读者点「反馈 / 建议」不会自动删卡。

空跑（不改文件、不调飞书）：

Actions → **Ops · retract or pause (dry-run)** → Run workflow。

| 输入 | 取值 |
|------|------|
| `action` | `retract` 或 `pause` |
| `card_id` | 撤稿必填，`evt-…` 或 `prac-…`。暂停留空 |
| `reason` | 必填 |
| `shift` | 暂停时填 `08:00` 或 `21:00`。不要填 `13:30` |

本地同样可以：

```bash
python3 scripts/ops_retract.py --action retract --card-id evt-… --reason "事实错误"
python3 scripts/ops_retract.py --action pause --shift 21:00 --reason "本班跳过"
python3 scripts/ops_retract.py --self-check
```

## 谁批准

睿批准。Alba 改卡并提交。不要在这个仓库里新增或修改飞书 webhook secret。

## 何时撤稿

- 事实错误，公开后会让人做错决定
- 侵权，或贴了不该公开的原文
- 一条传闻被误写成正式 P0（`priority=P0` 且 `status` 为 `confirmed` 或 `multi_source`）

不因为「不太喜欢」或读者一句意见就撤。

## 怎么改决策卡（`evt-`）

归档只增不减。删掉某天的文件或某张卡，CI 会失败。

1. 空跑确认 `card_id` 在哪个 `public/archive/YYYY-MM-DD.json`。
2. 改原卡，不要新发一条来「抵消」。
3. 写上 `correction`：`at`（北京时间）、`note`（改了什么）、需要时写 `previous_status`。
4. 误升正式 P0：把 `priority` 降为 `P1`，或把 `status` 改回 `rumor`，并在 `note` 里写明。
5. 侵权或必须下架的句子：从 `objective` / 标题里拿掉原文，改成一句下架说明，**保留原来的 `id`**。
6. `python3 scripts/generate_derived.py`，再 `python3 scripts/validate.py`。
7. 提交归档。飞书订阅群由人发一句。出站机器人见 `docs/FEISHU.md`，未配置 secret 时本来就是空跑，这里不要为了撤稿去配 secret。

## 怎么改实操卡（`prac-`）

1. 删掉 `public/practice/inbox/` 里对应 JSON。
2. 同时从 `public/practice.json` 的 `items` 里去掉同一 `id`。只删 inbox 时，派生脚本会把已经写进 `practice.json` 的条目留着。
3. 再跑派生和校验。

## 怎么暂停一班

本仓库的工作流停不了 Alba。

1. 空跑 `action=pause`，`shift` 用 `08:00`（每天主报）或 `21:00`（工作日晚班）。
2. Alba 这一班不写新卡、不把本班写成已发布。
3. 暂停原因记在飞书或私有池的私人主报里。不要把私人句子写进公开仓的 `DIGEST_LATEST.md`（该文件只是占位）。
4. 不要改 `state.json`。水位已弃用，见 `TIMELINE.md`。
5. 需要告诉读者时，人在飞书订阅群发一句。24 小时无新卡的健康检查仍可能响，暂停不会关掉它。
