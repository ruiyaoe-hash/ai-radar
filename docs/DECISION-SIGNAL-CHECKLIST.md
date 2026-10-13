# 验收清单（全量）

## Phase 1 — 必须合并进 PR
- [x] 事件模型：id/status/sources[{url,handle,role}]；status rumor|multi_source|confirmed；correction
- [x] schema_version；去掉 bullets（feed 生成时可由 objective 映射）
- [x] lens: 工具|赛道|模式|时机；UI 主过滤按 lens
- [x] P0-待证 vs 正式 P0 规则与 UI
- [x] JSON Schema + GH Actions CI：schema 合法；归档只增不减；feed 合法且条数≈items（`.github/workflows/ci.yml` 读取 `schemas/*.json`）
- [x] Actions 从 archive 派生 items.json、archive/index.json、feed.xml、lens feeds
- [x] deploy-pages 工作流只上传 `public/`（`.github/workflows/deploy-pages.yml`）；`data/` 副本已删除
- [ ] 删除根目录镜像：Pages 仍是 legacy `main` + `/`。改成 GitHub Actions 且部署成功后运行 `python3 scripts/retire_root_mirrors.py --i-switched-pages-to-actions`。在此之前保留根镜像，避免看板 404
- [x] 迁移现有卡片到事件模型（兼容旧字段）
- [x] Alba 工作流文档：只追加 archive 并 commit；其余 CI

## Phase 2
- [x] theses.json（5–10 条示例论点，可先占位）
- [x] so_what 结构（含 falsifier、thesis_id）；无 falsifier 则不写
- [x] 工具字段 try_url/access/integration/first_step/alternatives
- [x] 工具雷达页（采纳/试用/评估/暂缓）
- [x] 一手信源配置清单（RSS/Releases 等）写入 config
- [x] README「成功是什么样子」一节

## Phase 3
- [x] action 字段 tried|thesis_updated|shared|ignored（主人私用；可先本地 JSON，不强制公开）
- [x] sources 记分结构 + 脚本/文档
- [x] 周度决策备忘草稿生成（从 archive）
- [x] 「今日3条」纯文本块
- [x] 飞书 webhook 推送正式 P0 的 Actions（用 secret 占位 FEISHU_BOT_WEBHOOK，文档说明如何配置）
- [x] 健康检查：24h 无新卡告警（webhook 可选）
- [x] 班次与首报时差：每天 08:00 主报、工作日 21:00 晚班；`published_at` / `ingested_at` 建议填写、旧卡可缺

默认成功指标草案（README 可调）：N=3 决策/周；P0 命中率目标先写「待校准」；首报时差目标 <6h。
