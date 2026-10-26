# 打分、审核清单、快讯（B）

门槛和聚簇之后、L1 晋升之前。脚本是 `scripts/score_pool.py`。不调用云端模型。没有 `AI_RADAR_SCORE_LLM_URL` 时 `score.llm` 为 `null`，`method` 为 `rules`。把这个环境变量设上，也只写入 `skipped_reason=adapter_not_configured`，不会把正文 POST 出去。

生产分档仍是 v1（对照臂，control）。v2（多维实验分）默认只影子写入 `score.v2`，不改 `band`，也不因此多发快讯。要换成 v2 当档，把 `config.json` 的 `score.active_scorer` 改成 `v2`，或单次运行加 `--scorer v2`。Rui 没改之前，默认保持 v1。对照怎么跑见 [`score-ab-backtest.md`](./score-ab-backtest.md)。给人看的主路径是聊天里逐条选 A 或 B，清单在 `testdata/backtest/labeling-chat-pack.md`。

## 分

写在候选行的 `score` 上（私有池，不进公开仓）：

```text
value = clamp(
    prior × exp(-Δt / τ) × corroboration × velocity + actionability,
    0,
    1,
)
```

| 分量 | 含义 |
|------|------|
| `prior` | v1 对照臂仍用旧混合：`tier_mix` × `max(档位, role)` + (1−tier_mix) × 平滑命中率。这个数还会把高 `tier_prior` 和二手 `report` 揉在一起，所以**不要**把它当成证据等级。拆开的三个数写在下面。命中率 = `(命中 + hit_alpha) / (命中 + 否决 + hit_alpha + hit_beta)`。命中只算编辑晋升的 `promoted`。单纯自动快讯（`brief_id`，机器发的 L2）**不算**用户价值正反馈。否决只算编辑/质量类原因（`editor_skip`、`prefilter_block`、`not_opc_action`、`rumor_no_upgrade`、`media_alone`、`practice_not_steps`、`hot_signal_only`）。`low_score`、`duplicate_*`、`no_new_info`、`stale_old` 不进分母。还没决定的 `active` 不进分子也不进分母 |
| `decay` | 发表时间到 `--as-of` 的小时数。没有 `published_at` 时固定 0.55，不用入库时间假装很新 |
| `corroboration` | 独立证据，不是转载次数。同簇里已因 `duplicate_url`、`duplicate_event`、`no_new_info` 丢掉的行**不算**独立身份。有一手或官方 URL 时，按不同的一手 URL 计数（同源转载共用一个 URL，不加分）；没有一手 URL 时，才退回数独立账号。每多一个 +0.08，最多三个；簇内有一手再 +0.16。底是 0.72，上限 1。另两个数只记录、不乘进 v1：`spread`（传播面，说过这件事的账号，含转载）和 `independent_evidence`（独立一手 URL 的个数） |
| `velocity` | 没有收藏/点赞计数时为 1（RSS 不因此吃亏）。有计数时，`(bookmarks+bookmark_prior)/(likes+like_prior)` 和每小时收藏速度都按该作者在池里的样本归一，样本少时向先验收缩（`author_prior_n`）。丢弃行的计数也进基线 |
| `actionability` | 规则：步骤词、命令行、GitHub/GitLab 仓库链接。上限 `actionability_cap`。不是模型判分 |

默认常数在 `config.json` 的 `score`。当前 τ=36 小时，自动档 ≥ 0.52，人工档 ≥ 0.34。

只重打 `score_window_days`（默认 3）天内入库的行，旧池文件不会每轮被改写。已经带 `brief_id` 的行是一次发布决定，不再重打分，也不会因为衰减被丢成 `low_score`。互动计数是负数、非数字或 NaN 时按 0 读；`published_at` 比 `--as-of` 晚一小时以上时当作时间不可信（decay 0.55）。

## 三档

| `score.band` | `band_reason` | 池内 |
|--------------|---------------|------|
| `auto_brief` | `auto_primary` | 仍是 `active`。高分、**行本身**是 RSS 一手官方源（`score.official_source=true`），且不是实操车道。`scripts/derive_briefs.py` 可以写成公开快讯 |
| `review` | `review_score` / `review_practice` / `review_no_primary` / `review_not_official` / `review_deferred` / `review_p0` | 保持 `active`，或仍是 `deferred`（今日档先不上）。`--write-review` 把清单写到私有池 `review/YYYY-MM-DD.md`。`review_p0` 排在最前 |
| `drop` | `drop_low_score` | 只发生在仍是 `active` 的低分。`status_in_pool=dropped`，`drop_reason=low_score`，`notes` 里留 `score:low_score value=…`。schema 要求这条 notes 非空。已经 `deferred` 的行**不会**被改写成 `low_score` |

`review_not_official`：簇里有一手链接，但这一行自己不是 RSS 官方源。典型是 X 上的爆料帖和官方帖进了同一簇，或实验室自己的 X 账号。它们靠簇内印证拿到高分，但不会自动发布，必须人看。schema 用 `if band=auto_brief then official_source=true` 锁住这一条。

实操（`practice_handles`、`tier_prior=practice`、`lane_hint` 或 `participation=practice`）即使分高也是 `review_practice`，不会自动进快讯。班次打分之后跑 `scripts/project_public_lanes.py`：实操车道、分档仍是 `review`、收藏数达到 `score.bookmark_prior`，并且能抽出至少两步写完的中文做法时，写入 `public/practice/inbox/`，再由 `generate_derived.py` 并入 `practice.json`。步骤可以是编号或「首先 / 然后 / 接着 / 最后」，也可以是连续写成的中文操作说明：没有这些标记，只要正文里能拆出至少两个不同的具体动作，也过步骤门。短回复、纯观点、广告和没有具体动作的句子不算。公开卡上仍是拆开的步骤，不会把整段原文收成一步。X 帖标题经常是空的；正文里第一句能用的话会先当成临时标题，再走中文编辑层（`editorial_zh.edit_pair`，可选 `AI_RADAR_EDITORIAL_URL`）。英文或没写完的句子仍然不上站。跟读者闲聊的状态句（例如「没想到搞好了」「跟大家同步」）不能直接当标题；步骤还能照做时，改用步骤里的做法当标题，不把整条丢掉。`verified` 仍是 false，不由脚本改成已复核。不够两步、没有收藏计数、或收藏低于 `bookmark_prior` 的留在池里。同一 `prac-*` id 重跑不会再写一份。专题观察的领域进展走同一脚本：分析行（不是实操、不是自动快讯）标题为空时同样补一句，再要求中文标题和摘要。主题手册在没有素材时保持空列表，不预造骨架；长期看法和随笔仍由人写。

已经是 `editor_skip`、`promoted`、`rerouted`，或其它 `dropped` 的行不改状态、不覆盖原因。`low_score` 再跑 `annotate_gates` 也不会被抬回去。要重看，人先把原因改掉。例外只有强制 P0：窗口内、`drop_reason` 为 `low_score` 或 `stale_old`、而且规则对上的行，会被抬回 `active` 并标 `review_p0`。编辑否决不在此列。

`pending` / `wrong_lane` / `quota` / `quota_defer` 仍然不是 `drop_reason`。

这三件事不要写成同一个原因：

| 发生了什么 | 留在哪 | 不是 |
|------------|--------|------|
| 今天这期先不上（超过时效窗，或 RSS 回填不是今天） | `deferred`，`drop_reason` 仍是 null，`score.edition_eligibility=held_edition`，分档 `review_deferred` | 不是低价值，也不是重复 |
| 重复（同一 URL、同一短窗、或同簇没有新信息） | `duplicate_url` / `duplicate_event` / `no_new_info` | 不是「这篇不行」，也不拿去充独立证据 |
| 价值分不够 | 仅 `active` 行可成 `low_score` | 不是「过了今天的档期」 |

`edition_eligibility` 还有 `eligible`（可以进今天这期）和 `stale_window`（发表时钟已经老于门槛窗，但行仍是 active）。v1 的时间衰减仍用一个 τ=36 小时。按类型分开的时间只在 v2 的新鲜度里。

## 三个分开的数

v1 的 `components.prior` 是对照臂，仍可能让高档位盖住二手角色。判断时看这三个字段：

| 字段 | 含义 |
|------|------|
| `source_reliability`（信源可靠度） | 只看账号或机构先验：档位权重和编辑命中率。不掺 `role_guess` |
| `evidence_grade`（证据等级） | `primary` 0.95，`analysis` 0.72，`report` 0.42，角色空着是 0.5。T1 的二手报道等级仍是 0.42 |
| `content_value`（内容价值） | 等于 v1 的 `value`，是排序分，不是读者打分 |

## 强制 P0（Forced P0）

代码在 `scripts/force_p0.py`，由门槛和打分调用。例程仍可以再看一眼，但准绳是这段代码，不是 Alba 的口头清单。命中之后：

- 分档是 `review`，原因 `review_p0`，行上写 `force_p0`（`source=code`）
- 排进审核清单最前，并写私有池 `review/p0-YYYY-MM-DD.json`（没有正文）
- 发生在普通低分丢弃和「今天这期先不上」之前。`bypassed` 里会记下 `low_score` 或 `edition_date`
- **不**写公开归档，**不**写今日必看，**不**进自动快讯。要上公开卡仍是人开 PR
- 飞书默认仍只推已经由人写进归档的正式 P0。把 `AI_RADAR_P0_HOOK` 指到上面的 JSON，才会多打印或发送一条「待人审」。不设这个变量时，飞书行为与以前相同

三条规则（2026-10-22 漏报之后写死）：

1. **frontier_launch**：前沿实验室的新智能体、新产品线或新模型家族。包括研究预览（research preview），以及 Pro / Max 可以排队的候补（waitlist）。普通的发布说明、没有这些字样的，不会被抬成 P0。
2. **runtime_vuln**：厂商的远程代码执行（RCE）、未授权接管，或大规模运行时漏洞，并且写明了要升到的版本。不是 AI 技术栈也算，这是给访客的卫生提醒。只说「有洞」但没有版本号的，不强制。
3. **multi_a_tier**：同一个北京日历日、同一个簇里，至少两个 `a_tier` 账号，而且 v1 本来就会进人工档。必须摆出来让人明确晋升或跳过。文本像会改变这周的工具选择时，`default_action=promote`；否则建议 `skip`，但行仍留在队列里，直到人写成 `editor_skip` 或晋升。

回归夹具在 `testdata/p0/cases.json`：Claude Duet 研究预览，以及带升级版本的 PHP2Shell 一类运行时漏洞。

## 卡片文案 `card_copy`

公开页会按五个任务重排：今日重点、最新动态、工具决策、实战手册、专题观察。那一版页面是另一份改动。这里只保证打分结果能填卡片上的字，并且字里没有算法分数。

字段在候选行上，和 `score` 并列，不写进 `score.components`。公开卡片 schema 和快讯 schema 都留了同名的可选对象。已经发出去的归档和快讯不回填。

| 字段 | 给读者看的 | 不放什么 |
|------|------------|----------|
| `watch_reason` | 为什么值得看。固定短句 | 数字、分数、原文 |
| `evidence_label` | `官方原始信息` / `多源确认` / `尚待核实` | 证据等级那个 0–1 的数 |
| `suggested_action` | `立即行动` / `持续观察` / `暂缓` | 分档名字 |
| `high_priority_review` | 这一条要优先审 | 不是归档卡上的 `priority`（P0 / P1），也不是自动发布 |

标签怎么选：行本身是 RSS 一手官方源，写「官方原始信息」。否则同簇里至少两个未被当成转载丢掉的账号，写「多源确认」。剩下写「尚待核实」。

动作怎么选：带升级版本的运行时漏洞，或文本里已经在说这周可以换工具，写「立即行动」。研究预览、新产品线、候补名单，没有那句换工具的话，写「持续观察」。今天这期先不上、低分丢掉、或强制 P0 建议跳过，写「暂缓」。访客卡片上「建议行动」用同一组叫法：采纳或试用收成「立即行动」。条目自己写的具体动作（例如「今天升级」）留在 `so_what.action`，不改写成这三句。

`high_priority_review` 只在强制 P0 上为真。派生快讯时，只要这个标记为真、`force_p0.active`、或分档原因是 `review_p0`，整条不进 `briefs.json`。自动档快讯上的文案收窄成一句「官方源发布了新说明。」、证据「官方原始信息」、动作「持续观察」、标记 false。快讯仍不写 `so_what`、`priority`、`status`，也不写 `score`。

## v2 多维分（实验，不是最优）

`scripts/score_pool_v2.py`。五个 0–1 的维度，权重在 `config.json` 的 `score.v2`，加起来为 1：

```text
P = 0.30×importance + 0.25×novelty + 0.20×relevance + 0.15×actionability + 0.10×freshness
```

| 维度 | 现在怎么估（规则，不是模型） |
|------|------------------------------|
| importance（重要度） | 信源可靠度。前沿发布或带版本的运行时漏洞至少 0.86 |
| novelty（新颖度） | 转载把传播面抬高、却没有新的一手 URL 时下调 |
| relevance（相关度） | 产品发布和实操高一些。非 AI 的漏洞仍给访客卫生分 |
| actionability（可行动性） | 步骤、命令、仓库链接，外加「有版本可升」或「这周能换工具」 |
| freshness（新鲜度） | `exp(-年龄 / τ)`。τ 按类型：漏洞 18 小时，产品发布 30，教程 96，分析 72，其余 36。没有发表时间仍是 0.55 |

`confidence`（独立把握）单独做门，不掺进 P。二手且没有一手 URL 时封顶 0.4。强制 P0 同时绕过 P 的门槛和把握门槛，但仍然不能自动发布。

规则分永远会填上这些维度。云端模型只留了批处理 JSON 的形状（`llm_batch_stub`）：只有 id 和 URL，不 POST 正文。CI 不需要网络模型。本地若以后传入覆盖数字，缺的维度仍用规则值。

## 仍旧成立的限制

- RSS 的 batch 2（TechCrunch、HN、Reddit、trending 等）本阶段不抓，`--batch 2` 会拒绝。
- X 免费轨：Actions 没配 `X_BEARER_TOKEN` 时抓取软跳过，公开 CI 不因此失败。
- 自动快讯仍只锁官方 RSS 一手行。X 不自动写成快讯。强制 P0 只进审核，不进快讯。
- 公开仓和私有池仍分开。今日必看和已核验的实操仍要人开 PR。Pages 仍是静态站。

## 校准怎么写回

公开仓不放私人 action。

| 决定 | 写在哪 |
|------|--------|
| 上 L1 | 私有池该行 `promoted` + `archive_id`，公开卡写同一个 `candidate_id`。脚本不代做 |
| 否决 | `drop_reason=editor_skip`，`notes` 非空。打分和门槛都锁定这一行 |
| 只留快讯 | 保持 `active` 且 `band=auto_brief`。派生脚本写入 `brief_id` |
| 试过 / 忽略 | 未跟踪的 `owner-actions.local.json`，或飞书。`scripts/score_sources.py` 只有读到这份本地文件才加 `actions_taken`。公开 `public/owner-actions.json` 必须继续是空的 `example_only` |

审核清单在私有池，不进 `public/`。列是 cid、分档、分、handle、车道、是否一手、URL。不抄正文。

## 信源榜 `score_sources.py`

公开整数 `score` 的公式没改：`actions*5 + p0*2 + primary*3 + analysis - rumor - corrections*3`。

另两个字段：

- `hit_rate`：`(cards+2)/(cards+dropped+4)`。不传 `--pool-dir` 时 `dropped=0`，`pool_drops_included=false`，这是只有公开卡的幸存者视图
- `bookmark_like_ratio`：有互动计数才算 `(bookmarks+3)/(likes+5)`，丢弃帖的计数算进去。没有计数就是 `null`

`config.json` 里「按 bookmark 与 bookmark÷like 升降」指的是这个比值会进入候选 `velocity`，以及信源榜上的 `bookmark_like_ratio`。名单仍不自动改 `a_tier` / `practice_handles`。图谱上的收藏滚动在 [`atlas-live.md`](./atlas-live.md)，用的是同一套 `(bookmarks+3)/(likes+5)`，样本少时向先验收缩。

```bash
python3 scripts/score_sources.py --self-check
python3 scripts/score_sources.py
python3 scripts/score_sources.py --pool-dir ../ai-radar-pool
```

带了 `--pool-dir` 或本机 `owner-actions.local.json` 的那次 `public/source-scores.json` 不要提交。

## 快讯怎么被填上

`public/briefs.json` 里 `origin=archive_seed` 的条目摘自已经公开的归档，派生时保留。`origin=auto_brief` 只来自自动档：

- 摘要是第一句，最多 100 字，链接留在 `url`
- 去掉原始帖字段；`find_instruction_override` 命中的整条丢弃，不改写后硬发
- `url` 必须过 `safe_http_url`；页面仍用 `safeHref` + `textContent`
- URL 已经在 `public/archive/` 里的不上快讯（一条信号只占一层）
- 每轮最多 20 条自动档；页面上最多保留 60 条
- 只投射 `official_source=true` 且行本身是 RSS 一手的行，X 帖即使被标了 `auto_brief` 也不上
- 已发的自动快讯保留 7 天（北京日历日），之后分数衰减、掉出自动档也不会立刻从页面消失；超过 7 天自动下架
- 已发快讯的池行被人改成 `dropped`（比如 `editor_skip`），下一轮派生就撤下，这是人工否决权
- `brief_id` 一旦写上不再删除
- 不写 practice inbox

```bash
python3 scripts/derive_briefs.py --self-check
python3 scripts/derive_briefs.py --pool-dir ../ai-radar-pool --briefs public/briefs.json
```

## X 关注池

账号 = `config.json` 的 `practice_handles`，再加 `a_tier`（大小写不敏感去重）。

| 路径 | 什么时候 |
|------|----------|
| 手灌 | 和以前一样：`python3 scripts/shift_ingest_x_to_pool.py --fetch 抓取.json --pool-dir ../ai-radar-pool`，然后 `python3 scripts/score_pool.py --pool-dir ../ai-radar-pool --write-review` |
| 定时 | `.github/workflows/ingest-x-pool.yml`。密钥 `X_BEARER_TOKEN` 和 `AI_RADAR_POOL_TOKEN` 都在，才真正抓取并入池。缺任一密钥就警告后成功退出，公开 CI 不受影响 |
| 只看名单 | `python3 scripts/fetch_x_watch.py --dry-list` |

抓取脚本把 X API v2 的用户时间线收成 `ingest_x` 已经认识的 JSON（含 `public_metrics`）。令牌不入库、不打印。原始抓取文件写在 `$RUNNER_TEMP`，入池后删掉，不要提交。

- 用户 id 用 `users/by?usernames=` 一次查 100 个，查到的缓存在私有池 `state/x-since.json`，下次不再查
- 每个账号记 `since_id`，只拉上次之后的新帖
- 429 时按 `retry-after` / `x-rate-limit-reset` 等一次（最多 90 秒）；再被限流或要等更久，本轮停止请求，已抓到的照常入池
- 退出码：0 全部成功，2 部分账号失败（已抓到的入池，工作流最后标红提醒），1 一条都没拿到

X 帖不会进自动档（`review_not_official`）。过了实操两道门的，或写得清的分析，会经 `project_public_lanes.py` 进实战手册或专题观察，并跟着滚动 PR 上公开仓。没过门的仍然只留在私有池和审核清单。

## 工作流怎么写池、怎么上线

RSS 和 X 两个工作流共用 `concurrency: pool-writer`（`cancel-in-progress: false`），排队执行，不会互相 rebase 对方写了一半的 `candidates/`。

| 步骤 | 做什么 |
|------|--------|
| 检出 | 公开仓检出到 `site/`，私有池检出到旁边的 `pool/`。池必须在公开仓目录之外（`assert_shift_pool_dir`）。两个检出都 `persist-credentials: false` |
| 推池 | `scripts/pool_git_push.sh`。池令牌只在这一步的 env 里，用一次性 http 头推送，日志里打码。rebase 冲突说明有人手改了同一个文件：直接失败，不覆盖 |
| 推快讯 | `scripts/public_briefs_push.sh`。先跑 `validate.py`（只查公开输出，不做归档↔池的溯源比对）。过了才把 `public/briefs.json` 提交到滚动分支 `chore/auto-briefs`：从当前 `main` 尖端重建，这次提交只含这一份文件，再 `git push --force-with-lease`。`gh pr create` / `gh pr edit` 维持一个指向 `main` 的 PR。不推 `main`。若 `main` 上的 `briefs.json` 在本轮派生之后变过，且有 `POOL_DIR`，就以新的 `main` 为底重新派生再提交 |
| 上线 | 合并之后才上线。`deploy-pages.yml` 监听推送到 `main`，人把滚动 PR 合并后才会部署。ingest 不再调用 `gh workflow run deploy-pages.yml`。用 `GITHUB_TOKEN` 打开的 PR，`validate-and-derive` 可能先停在 Approve workflows，有写权限的人点一次才会跑；变绿后再合并 |

所有 `uses:` 都锁在 commit SHA 上，`validate.py` 会检查；`.github/dependabot.yml` 每周提更新。`run:` 里不直接写 `${{ }}`，一律经 `env:` 传。`X_BEARER_TOKEN` 只出现在抓取那一步。

仓库需要允许 GitHub Actions 创建 PR（Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests）。这不是分支保护的 bypass。`main` 仍然禁止直接推送，也禁止为了快讯给 Actions 加 bypass。

若不想每次在手机上点 Approve workflows：用只装在本仓的 GitHub App 令牌（`actions/create-github-app-token`）代替 `GITHUB_TOKEN` 去推 `chore/auto-briefs` 并开同一个滚动 PR。App 触发的 `pull_request` 会直接跑 `validate-and-derive`。快讯仍然不要直推 `main`。

## 定时不准时

GitHub `schedule` 会晚。RSS 与 X 工作流都有 `workflow_dispatch`。外部定时器（Cloudflare Workers Cron，或任何能发 HTTPS 的 cron）可以代为触发。本仓不部署这个 Worker。

令牌 `GH_DISPATCH_TOKEN`：只给公开仓 `ai-radar` 的 Actions 读和写。不要复用池令牌，也不要放进仓库。

```bash
curl -sS -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_DISPATCH_TOKEN}" \
  https://api.github.com/repos/ruiyaoe-hash/ai-radar/actions/workflows/ingest-x-pool.yml/dispatches \
  -d '{"ref":"main","inputs":{"mode":"live"}}'
```

RSS 把文件名换成 `ingest-rss-pool.yml`，body 只要 `{"ref":"main"}`。`mode=skip` 只确认 X 工作流骨架，不抓取。

## 自检

```bash
python3 scripts/score_pool.py --self-check
python3 scripts/score_pool_v2.py --self-check
python3 scripts/force_p0.py --self-check
python3 scripts/backtest_score_ab.py --self-check
python3 scripts/derive_briefs.py --self-check
python3 scripts/fetch_x_watch.py --self-check
python3 scripts/score_sources.py --self-check
python3 scripts/annotate_gates.py --self-check
python3 scripts/validate.py
```

`validate.py` 会把上面几项一并跑掉。没有 LLM 密钥时规则分必须能过。
