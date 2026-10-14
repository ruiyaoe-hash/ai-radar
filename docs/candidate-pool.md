# 候选池契约（candidate pool）

Phase 1 只定契约和全量入池。公开仓不存放候选正文、分数或弃稿流水。不训 ranker（排序模型），不做公开热度榜，本阶段也不改飞书 webhook。

## 管道

顺序固定：**ingest all（全量入池）→ annotate gates（门槛标注）→ cluster（聚簇）→ score（评分）→ promote（晋升）**。

先拦再入库是禁止的。日后会被标成 BLOCK（拦截）的帖子，这一步也要落一行。

| 步骤 | 谁做 | 写入 |
|------|------|------|
| ingest all | `scripts/ingest_x.py` | 稳定 `id`、规范化 URL、`status_in_pool=pending`。判断字段全部为空 |
| annotate gates | Alba | `prefilter`（PASS / BLOCK / UNKNOWN）、`status_in_pool`、真丢时的 `drop_reason` |
| cluster | 后一阶段 | `cluster_id` |
| score | 后一阶段 | 不在本 schema 里。分数不是发板条件 |
| promote | Alba | 公开仓 `public/archive/` 或 practice inbox；池内改为 `promoted`，并写 `archive_id` |

Alba **只填判断字段**，不手写 JSONL 骨架。`scripts/generate_derived.py` 仍只读公开归档和 practice inbox，不读池。Pages 仍只发布 `public/`。

## 私有仓和公开仓

| | 私有仓 `ai-radar-pool` | 公开仓 `ai-radar` |
|--|------------------------|-------------------|
| 放什么 | `candidates/YYYY-MM-DD.jsonl`、弃稿、第三方全文、门槛字段 | `schemas/candidate.schema.json`、本说明、`testdata/` 里的虚构夹具 |
| 不放什么 | 不进 Pages，不进公开 fork | 不放池 JSONL、评分原文、第三方全文、弃稿流水 |

生产环境的写入发生在 Actions 检出私有仓之后，令牌只授给 `ai-radar-pool`。本阶段脚本只写你传入的本地路径，方便 CI 夹具：

```bash
python3 scripts/ingest_x.py --self-check
python3 scripts/ingest_x.py --input fetch.json \
  --out /tmp/batch.jsonl \
  --ingested-at 2026-10-14T00:05:00Z
python3 scripts/ingest_x.py --pool-dir ../ai-radar-pool < fetch.json
```

`--out` 覆盖整个批次，重复的 status id 也各写一行。`--pool-dir` 合并进 `candidates/YYYY-MM-DD.jsonl`（日期按 `ingested_at` 的北京时间）。文件里已有的 `id` 不会被覆盖，所以重跑不会抹掉判断。脚本拒绝把输出写进 `public/`。

`id`（cid）形如 `cand-YYYYMMDD-` 加 12 位十六进制。日期是 `published_at` 的北京日历日，没有发表时间就用 `ingested_at`。有 status id 时，后缀是 `sha256("x-status:{id}")` 的前 12 位，因此 `twitter.com` 和 `x.com` 落到同一个 cid。

认这些原始形状：顶层数组，或 `items` / `data`（含 Twitter API v2 的 `includes.users`）/ `posts` / `tweets`，或单条帖子。没有 permalink、也没有数字 status id 的条目不编造 URL，记一行 `FETCH_GAP`，进程以退出码 2 结束；其余条目照常写入。

## `status_in_pool`（池内状态）

流转状态，可以不是丢弃。`ingest_x.py` 一律先写 `pending`。

| 值 | 含义 |
|----|------|
| `pending` | 已入池，门槛或评分还没做完 |
| `active` | 在池中，可以晋升 |
| `deferred` | 班次配额或时效延后。这不是真丢 |
| `rerouted` | 改道（例如 digest → practice）。这不是真丢 |
| `promoted` | 已经写进公开 archive 或 inbox，必须有 `archive_id` |
| `dropped` | 真丢弃，必须有 `drop_reason` |

## `drop_reason`（真丢弃原因）

只有 `status_in_pool=dropped` 时才能非空。其它状态必须是 `null`。

| 值 | 含义 |
|----|------|
| `prefilter_block` | 明显不是 AI，或明显无关 |
| `prefilter_unknown` | 材料不够，按策略不公开 |
| `not_opc_action` | 没有下一步决策动作 |
| `rumor_no_upgrade` | 传闻，而且升不了格 |
| `media_alone` | 只有媒体二手，挡住正式 P0 |
| `duplicate_event` | 同一事件已经有卡或候选 |
| `duplicate_url` | URL 规范化之后重复 |
| `stale_old` | 超出今日或看板的时效窗 |
| `no_reliable_time` | 没有可信时间，按策略不公开 |
| `no_new_info` | 同一簇在 7 日内没有实质性新进展 |
| `practice_not_steps` | 不像能照着做，步骤不够 |
| `hot_signal_only` | 只作讨论证据，不上决策板 |
| `editor_skip` | 编辑否决。`notes` 不能空。占比持续偏高要复盘门槛 |

这些**不是** `drop_reason`：`pending`、`wrong_lane`、`quota`、`quota_defer`。

- 配额或时效来不及：`status_in_pool=deferred`，`drop_reason=null`。
- 车道不对但能改道：`status_in_pool=rerouted`，改 `lane_hint`，`drop_reason=null`。
- 车道不对且无法改道：仍是真丢，用上表里的某一条（通常是带 `notes` 的 `editor_skip`），不要发明 `wrong_lane` 这个原因值。

## 晋升可追溯

`config.json` 的 `pool_traceability_since` 现为 `2026-10-15`。北京日历日达到这一天的新归档卡：

- 写 `candidate_id`，或
- 写 `promotion_path=emergency`（紧急晋升，可以没有池行）

2026-10-14 及更早的卡是遗留，不回填，也不要改已发布的 digest。

公开 CI 没有私有仓。它做两件事，并且**不**要求私有数据：

1. 上面的 `candidate_id` / `emergency` 指针检查（当前归档都早于截止日，所以是 0 张）。
2. 用 `testdata/` 的虚构夹具跑通「对上 `promoted` 才算数」。反例（没有 `candidate_id`、池行只是 `dropped`、把 `pending` / `wrong_lane` / `quota` 写成 drop reason）必须失败。

设置了 `AI_RADAR_POOL` 或 `POOL_DIR`，或者本机存在 `../ai-radar-pool/candidates/` 时，才会拿真实归档去对池快照。变量指到不存在的路径则失败。不要把 `testdata/pool` 当成生产快照。

## `practice_handles`（实操账号）

这 8 个账号已经从 `a_tier` 迁出，单独放在 `config.json` → `practice_handles`：

`op7418`、`vista8`、`lijigang`、`bcherny`、`trq212`、`mattpocockuk`、`addyosmani`、`ryolu_`

`a_tier` 继续只做决策和情报的信任先验。`dotey`、`simonw`、`shao__meng` 留在 `a_tier`。班次仍是每天 08:00 和工作日 21:00。derive 不读这张名单，所以已发布的 digest 不变。默认 `lane_hint=practice`、`participation=practice` 要到 Phase 3 的路由才强制；ingest 不替 Alba 填这两个字段。

公开实操卡的学习者字段在 `schemas/practice.schema.json`：`difficulty`（难度）、`prerequisites`（前置条件）、`estimated_time`（预计耗时）、`verified`（已验证）。已验证占比是集合指标，不是池字段。

## 私有仓空布局

本环境的令牌读不到 `https://github.com/ruiyaoe-hash/ai-radar-pool`（API 404 / `repository not found`），所以没能把下面的空目录推上去。有写权限时，私有仓只需要这些，不要把公开仓的 `testdata/` 或任何真实抓取拷过去当样例：

```text
README.md
candidates/.gitkeep
```

`candidates/README.md` 可以只有一句话：按北京时间命名 `YYYY-MM-DD.jsonl`，一行一个候选；判断字段由 Alba 回填，不要手改 `id`。

下面这段就是私有仓根上的 `README.md` 正文。

````markdown
# ai-radar-pool

Private candidate pool for AI Radar. Do not make this repo public.
Pages and the public `ai-radar` repo must not receive these JSONL files.

## Layout

```text
candidates/YYYY-MM-DD.jsonl
```

The date is the Asia/Shanghai calendar day of `ingested_at`. One JSON object per line.
The public contract is `schemas/candidate.schema.json` in `ruiyaoe-hash/ai-radar`.

## Ingest contract

1. Alba passes the raw X fetch to `scripts/ingest_x.py` from the public repo.
   Do not hand-author JSONL skeletons.
2. The script writes every item with `status_in_pool=pending` and null judgment fields.
   A post that will later be BLOCK still gets a row. Items with no permalink and no
   status id are `FETCH_GAP` on stderr (exit 2), not silent skips.
3. Production command, after this repo is checked out:

   ```bash
   python3 /path/to/ai-radar/scripts/ingest_x.py \
     --pool-dir "$PWD" \
     --ingested-at 2026-10-14T00:05:00Z \
     < fetch.json
   ```

   `--pool-dir` writes every new row, including two rows that share an id.
   If that id is already in the day's file, the existing row stays, judgment included.
4. Alba then fills only judgment fields: `prefilter`, `status_in_pool`,
   `drop_reason` (true drops only), `lane_hint`, `participation`, `tier_prior`,
   `source.role_guess`, `notes`, and on promotion `archive_id` plus
   `promotion_path=normal`.
5. `drop_reason` is null unless `status_in_pool=dropped`. `no_new_info` is a true drop.
   `pending`, `wrong_lane`, `quota`, and `quota_defer` are not drop reasons.
   Delay is `deferred`. A lane change that can be routed is `rerouted`.
6. Actions that fetch RSS later must use a fine-grained token scoped to this repo only.

`--out` on the public repo is for local fixtures. Do not point it at `ai-radar/public/`.
````
