# v1 / v2 对照回测（A/B backtest）

给 Rui 用。目的是拿同一批候选，看旧分（v1，现在的生产档）和新分（v2，多维实验分）哪里不一致，再由人标「这条该不该被看见」。脚本不发快讯，不写公开归档，也不访问私有池以外的网络。

英文词在这里第一次出现时带着中文：v1 是对照臂（control），v2 是实验臂。影子（shadow）的意思是 v2 只被写下来，不改今天的分档。

## 现在生产怎么走

`config.json` 里 `score.active_scorer` 是 `v1`，`score.shadow_v2` 是 `true`。每日打分仍按 v1 决定自动快讯、人工档和低分丢弃。v2 的 P、把握和五个维度写在 `score.v2`。强制 P0 两条臂都会送进 `review_p0`，都不会自动发布。

权重是起点，不是调好的最优：

```text
P = 0.30×重要度 + 0.25×新颖度 + 0.20×相关度 + 0.15×可行动性 + 0.10×新鲜度
```

新鲜度的时间常数按类型分开：漏洞 18 小时，产品发布 30，教程 96，分析 72，其余 36。细节在 [`score-and-briefs.md`](./score-and-briefs.md)。

## 从私有池导出样本

在公开仓目录外的私有池里，挑几天的候选文件。不要把正文提交回公开仓。

```bash
# 例：把两天的行收成一份本地 JSONL。路径按你的池来。
cat ../ai-radar-pool/candidates/2026-10-21.jsonl \
    ../ai-radar-pool/candidates/2026-10-22.jsonl \
    > /tmp/pool-sample.jsonl
```

行里本来就有 `snippet`。对照表不抄正文，只留 cid、URL 和账号。导出文件留在本机。

没有私有池时，用仓库里的虚构样本：

```bash
python3 scripts/backtest_score_ab.py \
  --input testdata/backtest/sample.jsonl \
  --as-of 2026-10-22T12:00:00Z \
  --out-dir /tmp/ai-radar-ab
```

CI 跑的是 `python3 scripts/backtest_score_ab.py --self-check`，不读私有池。

## Rui 怎么标

先生成空表（列已经对齐）：

```bash
python3 scripts/backtest_score_ab.py \
  --input /tmp/pool-sample.jsonl \
  --emit-template /tmp/labels.csv
```

仓库里有一份空白例子 `testdata/backtest/labels.template.csv`，和一份只用于自检的填好例子 `testdata/backtest/labels.sample.csv`。填的时候用 `1` 或 `0`，拿不准就留空。留空的格子不进那个指标的分子或分母。

| 列 | 填什么 |
|----|--------|
| `important` | 这周值得看见 |
| `duplicate` | 和已经留下的是同一件事的转载 |
| `low_value` | 价值低。今天这期先不上（时效）不要填在这里 |
| `actionable` | 看得懂下一步（升级、试用、换工具） |
| `evidence_sufficient` | 一手或足够的独立证据已经有了 |
| `should_p0` | 应该进强制 P0 审核，而不是被低分或档期吞掉 |
| `event_at` | 事情发生的时间，ISO-8601 UTC。没有就空着 |
| `notes` | 你自己的短句。不要粘贴原文 |

`low_value` 和「今天这期先不上」是两件事。后者在池里是 `deferred`，不要标成低价值。

## 怎么跑对照

```bash
python3 scripts/backtest_score_ab.py \
  --input /tmp/pool-sample.jsonl \
  --labels /tmp/labels.csv \
  --as-of 2026-10-22T12:00:00Z \
  --out-dir /tmp/ai-radar-ab
```

`/tmp/ai-radar-ab/` 里会有：

- `comparison.csv` / `comparison.md`：cid、URL、账号、v1 的分和档、v2 的五个维度、P、把握、档、内容类型、P0 标记、卡片文案（证据标签、建议动作、是否优先审、为什么值得看）、两边档是否不一致。文案列是给人看的字，不是另一套分
- `metrics.md` / `metrics.json`：下面这些数。没贴标签时不写这两个文件

`--as-of` 用你导出那天的时钟，衰减才和当时接近。

## 指标怎么读

| 名字 | 含义 |
|------|------|
| `p0_recall` | 你标了 `should_p0` 的行里，有多少被标成强制 P0 |
| `p0_precision` | 机器标成强制 P0 的行里，有多少你也认为该进 |
| `auto_brief_precision_v1` / `_v2` | 自动档里，你标了重要、且不是重复也不是低价值的比例 |
| `topk_useful_v1` / `_v2` | 按 v1 分或 v2 的 P 取前 K 条（默认 5）里，重要的比例 |
| `false_suppress_v1` / `_v2` | 你认为重要、不是重复也不是低价值，却被打成 drop 的条数 |
| `false_promote_v1` / `_v2` | 你标了低价值或重复，却进了自动档的条数 |
| `discovery_delay_hours_mean` | 有发表时间和入库时间时，`ingested_at − published_at` 的平均小时数 |
| `event_delay_hours_mean` | 你填了 `event_at` 时，`ingested_at − event_at` 的平均小时数 |
| `review_cost_proxy_v1` / `_v2` | 人工档条数。这是审阅成本的代理，不是小时数 |

分母是 0 时，率是空的，不会写成 0。样本里的普通官方说明被故意标成「不重要」，用来确认「误抬进自动档」这格能算出来。那不是生产上的新政策。

看不一致那一列：v1 丢掉、v2 留下，或反过来。强制 P0 两边都应是人工档。若 v2 的自动档比 v1 更多，先不要把 `active_scorer` 改成 v2。

## 仍旧成立的限制

- RSS batch 2 仍不抓。
- X 没配 bearer（`X_BEARER_TOKEN`）时，Actions 抓取软跳过。
- 自动快讯仍只来自官方 RSS 一手行。优先审的行不进自动档。
- 公开仓和私有池仍分开。今日必看和已核验实操仍要人开 PR。
