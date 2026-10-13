# AI Radar 全量改造规格（主人确认 · 2026-10-11）

将「情报时间线」升级为「决策信号系统」。以下为完整实施规格。

## 一、北极星：可行动信号数
- 卡片加主人私用 `action`：`tried` / `thesis_updated` / `shared` / `ignored`
- 每周回看；连续无动作的信源/标签/P0 类型视为噪声

## 二、judgment → 结构化 so_what（可证伪）
```json
"so_what": {
  "lens": "赛道",
  "impact": "...",
  "action": "观察",
  "window": "未来 1–2 个季度",
  "confidence": "中",
  "falsifier": "若…则此判断作废",
  "thesis_id": "T-003"
}
```
- 写不出 falsifier 就不写 so_what
- theses.json 维护 5–10 条长期论点；卡片挂支持/反对证据
- 到期打分：命中/未命中/待定

## 三、事件模型（一事件多来源）
- id: evt-YYYYMMDD-slug（系统生成，作 RSS guid 与永久链接）
- status: rumor | multi_source | confirmed
- sources[]: url, handle, role=primary|analysis|report
- 标题跟一手；拆解作延伸阅读
- 升级更新原卡 + correction，不新发重复卡
- rumor 最高 P0-待证；一手或两独立源升正式 P0

## 四、双轴：tag + lens
- tag：事件类型（给 Agent）
- lens：工具/赛道/模式/时机（人主过滤）
- P0：今天没看到会做错或错过决策

## 五、工具字段 + 工具雷达页
lens=工具 时：try_url, access, integration, first_step, alternatives
常驻 Tech Radar：采纳/试用/评估/暂缓

## 六、信源
- 补一手：实验室博客/changelog RSS、GitHub Releases、HF Trending、arXiv、PH AI、融资并购 RSS
- 信源记分：P0 数、首报、误报、被采取行动
- 班次（北京时间 Asia/Shanghai，不写美西钟点；11 月 1 日 PDT→PST 时差 15h→16h）：每天 08:00 主报（美西上一工作日收盘窗口）；周一至周五 21:00 晚班短报（中国白天 + 美东早晨）。13:30 午间主报已取消。05:30 静默班延至飞书出站 webhook 可用
- 首报时差：`lead_lag_hours` 仍是按下一班假定的数，已有值不改。新卡写 `published_at`（信源原发，ISO-8601 UTC；没有时间就省略）和 `ingested_at`（首次写入归档）。两枚都在时，实测时差 = `ingested_at` − `published_at`

## 七、分发
- 周度决策备忘（自动起草+人工改定）
- 「今日 3 条」纯文本一键复制
- 飞书：自定义机器人 webhook 主动推正式 P0（非待证）；Secrets 放 GH Actions

## 八、质量闭环
- 月度 P0 复盘；周漏报审计；correction 公开划线

## 九、工程
- Alba 只追加写 archive/YYYY-MM-DD.json 并提交
- GH Actions：Schema 校验；归档只增不减；派生 items/index/feed/按 lens feed/工具雷达/周报草稿；deploy-pages 只发 public/；删根镜像与 data/；24h 无新卡告警
- 去掉 bullets，仅 objective；schema_version
- CI 三测：Schema；归档单调；feed 合法且条数一致

## 十、推进顺序
1 地基 → 2 差异化 → 3 闭环分发

## 成功样子（写入文档开头）
主人每周因 Radar 做出至少 N 个工具或赛道决策；P0 事后命中率不低于 X%；重大发布首报时差在 Y 小时内。（N/X/Y 先给合理默认并在 README 标明可调）
