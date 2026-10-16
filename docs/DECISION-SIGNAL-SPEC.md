# AI Radar → 决策信号系统（主人确认全量开发）

（用户 2026-10-11 完整建议原文归档，实施以此为准。）

## 北极星
可行动信号数：卡片 → tried / thesis_updated / shared / ignored；每周回看。

## 阶段1 地基
事件模型（自有 id、sources[].role、status rumor/multi_source/confirmed）、lens、Schema+CI、Actions 派生发布、删除根镜像与 data/ 三份副本；bullets 去掉；schema_version。

## 阶段2 差异化
theses.json、so_what（lens/impact/action/window/confidence/falsifier/thesis_id）、工具字段+工具雷达页、P0-待证、一手信源。

## 阶段3 闭环分发
action 记录、信源记分、首报时差、漏报审计、周度决策备忘、飞书 webhook 主动推正式 P0。班次（北京时间）：每天 08:00 主报，周一至周五 21:00 晚班；13:30 主报已取消；05:30 静默班待飞书出站 webhook。实测时差用 `ingested_at` − `published_at`。

详见用户消息全文（聊天 t58u）。

## 人读层

主报和卡片里给人看的句子，按 [`AIHOT对接与表达规范-v0.md`](./AIHOT对接与表达规范-v0.md)。机器字段仍留在 JSON。P0 定义、一手门闩、`falsifier`、`media_alone` 不放宽。
