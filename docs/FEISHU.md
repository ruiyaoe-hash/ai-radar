# 飞书

## 整站反馈

侧栏「说明」末尾的「反馈 / 建议」，以及首页、关于、订阅页脚的更正入口，都打开同一份公开问卷（新标签页）：

https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd

这是整站意见，不是单卡赞踩，也还没有订阅群入口。站点只放链接：问卷在飞书侧匿名填写，不向飞书发脚本请求，也不放宽 CSP 的 `connect-src` / `form-action`。导航地址先经 `safeHref()`。

## 出站推送

## Secret

仓库 → Settings → Secrets and variables → Actions → New repository secret：

- Name: `FEISHU_BOT_WEBHOOK`
- Value: 飞书自定义机器人 webhook 完整 URL

## 行为

工作流：`.github/workflows/feishu-and-health.yml`  
（`docs/workflows/` 里是同一份副本，方便在没有 workflow 权限时审阅。）

- 推送 **正式 P0**（`priority=P0` 且 `status` 为 `confirmed` 或 `multi_source`），**不推** P0-待证（rumor）
- **24h 无新卡** 健康告警；同一告警至少间隔 20 小时，避免每 6 小时重复刷屏
- 已推送的事件 id 写在 Actions cache（`.feishu-notify-state.json`），不写进 `state.json` 水位
- 未配置 secret 时脚本 dry-run，**不会**把 id 标成已发送，CI 不失败

## 本地试跑

```bash
export FEISHU_BOT_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/...'
python3 scripts/feishu_notify.py
```
