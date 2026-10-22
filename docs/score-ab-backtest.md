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

没有私有池时，聊天用的虚构样本已经在仓库里。CI 跑的是 `python3 scripts/backtest_score_ab.py --self-check`，不读私有池。

## Rui 怎么标

主路径是聊天，不是表。Alba 把短例子一条条推给 Rui。Rui 每条只选 A 或 B：A 是现在的 v1 决定，B 是实验的 v2 决定。两边一样时回「相同」。攒够之后，Alba 用回执汇总偏好。

可直接粘贴的清单是 [`testdata/backtest/labeling-chat-pack.md`](../testdata/backtest/labeling-chat-pack.md)。里面 31 条虚构例子，编号从 1 到 31。研究预览那条，以及带升级版本的运行时漏洞，都在里面，而且标成优先审。清单不写分数，也不抄原文。每条是一句「发生了什么」，然后左右各四个字：档、优先、动作、证据。

私有池上要重新出一份时：

```bash
python3 scripts/backtest_score_ab.py \
  --input /tmp/pool-sample.jsonl \
  --as-of 2026-10-22T12:00:00Z \
  --out-dir /tmp/ai-radar-ab
```

`--out-dir` 里会有 `labeling-chat-pack.md`。行上如果带了 `ab_line`，那一句会变成「发生了什么」；这个字段不进打分。没有 `ab_line` 时，那一行会写「这条没有单独的一句说明。」

回执是纯文本，一行一条：

```text
1 相同
19 B
29 A
31 A
```

也可以是两列表 `n,choice`。然后：

```bash
python3 scripts/backtest_score_ab.py \
  --pack \
  --picks /tmp/picks.txt \
  --out-dir /tmp/ai-radar-ab
```

`--pack` 用仓库里那 31 条。汇总写到 `picks-metrics.md`。只有两边不同、而且回了 A 或 B 的条目才算偏好。回「相同」表示接受两边共同的决定，不记成某一边赢。一条都还没分出胜负时，偏好是空的，不会写成 0。

仓库里的小样本 `testdata/backtest/sample.jsonl` 仍给自检用，六行就够看强制 P0 和误抬进自动档。

## 批量时的多列表

要一次导出很多列时，仍可用 CSV。Rui 的主路径仍是上面的 A 或 B。

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

- `labeling-chat-pack.md`：给聊天粘贴的编号清单。每次 `--out-dir` 都会写。行上的 `ab_line` 变成「发生了什么」；没有这句时，清单里会标明这行没有单独说明
- `comparison.csv` / `comparison.md`：批量用。cid、URL、账号、v1 的分和档、v2 的五个维度、P、把握、档、内容类型、P0 标记、卡片文案，以及聊天里那行 A/B 对照。文案列是给人看的字
- `picks-metrics.md` / `picks-metrics.json`：有 `--picks` 才写。这是聊天回执的汇总
- `metrics.md` / `metrics.json`：贴了多列表标签才写。没贴就不写

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

聊天汇总里看 `a_prefer_rate` 和 `b_prefer_rate`：在两边真有差别的条目上，Rui 更常选哪一边。强制 P0 在这套权重下两边经常相同，那些条回「相同」就行，表示接受「优先审、不自动发」。

多列表上仍可看不一致那一列：v1 丢掉、v2 留下，或反过来。强制 P0 两边都应是人工档。若 v2 的自动档比 v1 更多，先不要把 `active_scorer` 改成 v2。

## 仍旧成立的限制

- RSS batch 2 仍不抓。
- X 没配 bearer（`X_BEARER_TOKEN`）时，Actions 抓取软跳过。
- 自动快讯仍只来自官方 RSS 一手行。优先审的行不进自动档。
- 公开仓和私有池仍分开。今日必看和已核验实操仍要人开 PR。
