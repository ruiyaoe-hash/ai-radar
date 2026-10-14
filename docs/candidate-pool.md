# 候选池契约（candidate pool）

Phase 1 定契约和全量入池。Phase 2 把 L0 门槛和 L2 聚簇写成可跑函数，并加上源分级表。Phase 4 用 Actions 把 T1 实验室 RSS 写进私有池。公开仓不存放候选正文、分数或弃稿流水。不训 ranker（排序模型），不做公开热度榜，也不改飞书 webhook。

## 管道

顺序固定：**ingest all（全量入池）→ annotate gates（门槛标注）→ cluster（聚簇）→ score（评分）→ promote（晋升）**。

先拦再入库是禁止的。日后会被标成 BLOCK（拦截）的帖子，这一步也要落一行。

| 步骤 | 谁做 | 写入 |
|------|------|------|
| ingest all | `scripts/ingest_x.py`；RSS 用 `scripts/ingest_rss.py` | 稳定 `id`、规范化 URL、`status_in_pool=pending`。判断字段全部为空 |
| annotate gates | Alba 跑 `scripts/annotate_gates.py` | `prefilter`（PASS / BLOCK / UNKNOWN）、`status_in_pool`、真丢时的 `drop_reason`、`tier_prior`、能对上的 `source.role_guess` |
| cluster | 同一次脚本里的 L2 | `cluster_id`。标题相似不是唯一键 |
| score | 后一阶段 | 不在本 schema 里。分数不是发板条件 |
| promote | Alba | 公开仓 `public/archive/` 或 practice inbox；池内改为 `promoted`，并写 `archive_id` |

机器门槛和聚簇由脚本写回。Alba 不手写 JSONL 骨架，也不手填这批门槛字段。晋升、`editor_skip`（编辑否决）、车道仍由 Alba 写。`scripts/generate_derived.py` 仍只读公开归档和 practice inbox，不读池。Pages 仍只发布 `public/`。

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

## L0 门槛（annotate gates）

Alba 在全量入池之后跑 `scripts/annotate_gates.py`。脚本读候选行（JSONL 或列表），把判断写回私有池，不新建公开卡，也不打分。

一次运行的内部顺序是：L0 规则 → L2 聚簇 → 用 `cluster_id` 补 `no_new_info`。对外仍是「先门槛、再聚簇」；`no_new_info` 必须看见簇，所以放在同一次运行的最后。BLOCK 和 UNKNOWN 都留在池里。

已是 `promoted`、`rerouted`，或 `drop_reason=editor_skip` 的行不改状态。空的 `cluster_id` 会补上。`--only-pending` 只处理仍为 `pending` 且 `prefilter` 为空的行，给 RSS 工作流用，避免盖掉已经标过的行。

| 规则 | 默认行为 | `drop_reason` / `status_in_pool` |
|------|----------|----------------------------------|
| URL 规范化 | 去掉 tracking query，统一成 https | 同一 `id` 或同一 `url_norm` → `dropped` + `duplicate_url` |
| 同源短窗 | 默认 30 分钟。同一 channel+handle，且没有新外链、正文也没有至少 3 个新词 | `dropped` + `duplicate_event`。短窗里如果带来新外链，留下 |
| 时效 | 发表时间早于 `--as-of` 超过 48 小时（可配） | **默认 `deferred`，`drop_reason` 仍是 null**。`--stale-policy drop` 才是 `stale_old` |
| RSS 回填 | `channel=rss` 且发表日的北京日历日早于 `--as-of` | `deferred`，notes 写 `rss_backfill_not_today`。这不是 `stale_old`，也不占今日 |
| 无可信时间 | 没有 `published_at` | **默认 `prefilter=UNKNOWN` 且 `pending`，不静默跳过**。`--no-time-policy drop` 才是 `no_reliable_time` |
| 预筛三态 | 宽召回。只有明显非 AI（例如天气、菜谱、球赛，且没有模型词）才 BLOCK | `BLOCK` → `dropped` + `prefilter_block`。材料够且像 AI，或低门槛源，为 `PASS` |
| 信任先验 | `config.json` 的 `a_tier` / `practice_handles`，加上 `config/source_tier_map.json` | 写入 `tier_prior` 和能对上的 `role_guess`。不在表里**不**硬排除 |
| 媒体 alone | `role=report` 且候选 URL 和外链都不是 primary / 官方 | 默认留 `active`，notes 写明不能升正式 P0。notes 里有 `attempt_formal_p0` 才 `dropped` + `media_alone` |
| 无新进展 | 同簇 7 日内没有新外链，正文新词也不到 3 个 | `dropped` + `no_new_info`（这是真丢） |
| 安全 | 只收 http(s)，沿用 `generate_derived.safe_http_url` | 其它协议 → `dropped` + `prefilter_block` |

`deferred` 和 `rerouted` 仍然不是 `drop_reason`。脚本不写 `wrong_lane`、`quota`、`quota_defer`。

```bash
python3 scripts/annotate_gates.py --self-check
python3 scripts/annotate_gates.py --input rows.jsonl \
  --out /tmp/annotated.jsonl \
  --as-of 2026-10-14T12:00:00Z
python3 scripts/annotate_gates.py --pool-dir ../ai-radar-pool --as-of 2026-10-14T12:00:00Z
python3 scripts/annotate_gates.py --pool-dir ../ai-radar-pool --only-pending
```

`--out` 和 `--pool-dir` 不能同时拿来当输入。脚本拒绝把结果写进 `public/`。夹具在 `testdata/gates/cases.json`，正文都是虚构句。

## L2 轻量聚簇（clustering）

顺序固定，标题永远不是唯一键：

1. **共享外链**。规范化之后相同就同簇。文章自己的 URL 算簇键；X 的 status 链接不算，因为每条帖子都唯一。两条没有 title 的帖子只要指向同一篇实验笔记，就会得到同一个 `cluster_id`。
2. **实体规则表** `config/entity_rules.json`。CVE、`ExampleModel-9` 这类 `cluster_alone=true` 的命中本身成簇。`cluster_alone=false`（例如 `FixtureLoose-Name`）必须再叠加标题相似才合并。
3. **标题相似**只作为第 2 步的附加条件。没有 title 就跳过，不报错。两条只有标题相像、没有共同外链也没有实体命中的行，簇 id 不同。

`cluster_id` 形如 `clu-` 加 12 位十六进制，由本簇最小的外链、否则最小的实体键、否则最小的候选 `id` 哈希得到。同簇里已经有 `promoted` 或 `archive_id` 时，其它还没丢的行 notes 写 `correction_path`，指向那张公开卡。本阶段不写新卡，也不改原卡。

## 源分级（source tier）

`config/source_tier_map.json` 把 domain、X handle、`sources.json` 的 id 映射到 `tier_prior` + `role_guess`。`config.json` 里的 `source_tier_map` 指到这个文件。

| 档 | 例子 | 门槛 |
|----|------|------|
| T1 / `primary` / `a_tier` | OpenAI、Anthropic、DeepMind、Hugging Face 博客，以及 `/openai/`、`/anthropics/` 的 GitHub Releases | 低。空摘要也可以 PASS。不是入库硬门 |
| `practice` | `practice_handles` 那 8 个账号 | 低。只写 `tier_prior=practice`。车道要到 Phase 3 才强制 |
| T3 / `report` | TechCrunch、HN、Reddit | 高。预筛仍放行；正式 P0 被媒体 alone 挡住 |
| 不在表里 | 任意其它 handle 或域名 | 不排除。像 AI 就 PASS，正文为空才 UNKNOWN |

高门槛不等于拦截。名单外的行不会因为「没录入」被丢掉。

## RSS 入池（Phase 4）

`scripts/ingest_rss.py` 只拉 `public/config/sources.json` 里 `fetch_batch=1` 的六条：`openai-blog`、`anthropic-news`、`deepmind-blog`、`huggingface-blog`、`gh-releases-openai`、`gh-releases-anthropic-sdk`。

TechCrunch、HN、Reddit、trending、arXiv、Product Hunt、融资汇总是 `fetch_batch=2`，本阶段不抓。`--batch 2` 会直接拒绝。

抓下来的行和 `ingest_x` 同一套骨架：`channel=rss`，`status_in_pool=pending`，判断字段为空。`source.handle` 用 sources.json 的 id，方便对上分级表。feed 为空时日志写「无更新」。没有 http(s) 链接的条目是 `FETCH_GAP`（退出码 2），其余照常写入。不抓文章正文，description / summary 截到 2000 字，只进私有池。

公开 CI 只跑 `--self-check`（`testdata/rss/` 里的虚构 feed）。定时拉取在 `.github/workflows/ingest-rss-pool.yml`，不挂在 `pull_request` 上。密钥、轮换和「令牌不得写公开仓」见 `docs/rss-pool-ingest.md`。

```bash
python3 scripts/ingest_rss.py --self-check
python3 scripts/ingest_rss.py --fixture testdata/rss/openai-blog.xml \
  --source-id openai-blog --out /tmp/rss.jsonl \
  --ingested-at 2026-10-14T12:00:00Z
python3 scripts/ingest_rss.py --pool-dir ../ai-radar-pool
```

工作流在入库之后对私有池跑 `annotate_gates.py --only-pending`。不自动晋升，不改 `generate_derived.py`。

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
4. After ingest, run `scripts/annotate_gates.py --pool-dir "$PWD"` from the public repo.
   It fills `prefilter`, `status_in_pool`, true-drop `drop_reason`, `tier_prior`,
   `source.role_guess`, and `cluster_id`. It does not promote.
5. Alba then fills what the script does not: `lane_hint`, `participation`,
   `editor_skip` (with a note), and on promotion `archive_id` plus
   `promotion_path=normal`. Do not hand-edit `id`.
6. `drop_reason` is null unless `status_in_pool=dropped`. `no_new_info` is a true drop.
   `pending`, `wrong_lane`, `quota`, and `quota_defer` are not drop reasons.
   Delay is `deferred`. A lane change that can be routed is `rerouted`.
7. RSS batch 1 is ingested by GitHub Actions with `AI_RADAR_POOL_TOKEN`.
   That token may write only this private repo. It must not push pool JSONL
   into public `ai-radar`. Empty feeds log `无更新`. See `docs/rss-pool-ingest.md`
   in the public repo.

`--out` on the public repo is for local fixtures. Do not point it at `ai-radar/public/`.
````
