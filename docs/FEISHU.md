# 飞书推送配置

## Secret

仓库 → Settings → Secrets and variables → Actions → New repository secret：

- Name: `FEISHU_BOT_WEBHOOK`
- Value: 飞书自定义机器人 webhook 完整 URL

## 行为

工作流：`.github/workflows/feishu-and-health.yml`

- 推送 **正式 P0**（`priority=P0` 且 `status` 为 `confirmed` 或 `multi_source`），**不推** P0-待证（rumor）
- **24h 无新卡** 健康告警
- 未配置 secret 时脚本 dry-run，CI 不失败

## 本地试跑

```bash
export FEISHU_BOT_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/...'
python3 scripts/feishu_notify.py
```
