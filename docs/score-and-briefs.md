# 打分、审核清单、快讯（B）

门槛和聚簇之后、L1 晋升之前。脚本是 `scripts/score_pool.py`。不调用云端模型。没有 `AI_RADAR_SCORE_LLM_URL` 时 `score.llm` 为 `null`，`method` 为 `rules`。把这个环境变量设上，也只写入 `skipped_reason=adapter_not_configured`，不会把正文 POST 出去。

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
| `prior` | `tier_mix` × 档位权重 + (1−tier_mix) × 平滑命中率。档位来自 `tier_prior` / `role_guess`（T1、a_tier 高，T3 低，名单外 0.48）。命中率 = `(命中 + hit_alpha) / (命中 + 否决 + hit_alpha + hit_beta)`。命中 = `promoted` 或已带 `brief_id`。否决只算编辑/质量类原因（`editor_skip`、`prefilter_block`、`not_opc_action`、`rumor_no_upgrade`、`media_alone`、`practice_not_steps`、`hot_signal_only`）。`low_score`（衰减）、`duplicate_*`、`no_new_info`、`stale_old` 说明的是时机，不是信源好坏，**不进分母**。还没决定的 `active` 不进分子也不进分母 |
| `decay` | 发表时间到 `--as-of` 的小时数。没有 `published_at` 时固定 0.55，不用入库时间假装很新 |
| `corroboration` | 同簇里 `prefilter=PASS` 的独立 handle（或无 handle 时的 URL）数，每多一个 +0.08，最多三个；簇内有一手/官方链接再 +0.16。底是 0.72，上限 1 |
| `velocity` | 没有收藏/点赞计数时为 1（RSS 不因此吃亏）。有计数时，`(bookmarks+bookmark_prior)/(likes+like_prior)` 和每小时收藏速度都按该作者在池里的样本归一，样本少时向先验收缩（`author_prior_n`）。丢弃行的计数也进基线 |
| `actionability` | 规则：步骤词、命令行、GitHub/GitLab 仓库链接。上限 `actionability_cap`。不是模型判分 |

默认常数在 `config.json` 的 `score`。当前 τ=36 小时，自动档 ≥ 0.52，人工档 ≥ 0.34。

只重打 `score_window_days`（默认 3）天内入库的行，旧池文件不会每轮被改写。已经带 `brief_id` 的行是一次发布决定，不再重打分，也不会因为衰减被丢成 `low_score`。互动计数是负数、非数字或 NaN 时按 0 读；`published_at` 比 `--as-of` 晚一小时以上时当作时间不可信（decay 0.55）。

## 三档

| `score.band` | `band_reason` | 池内 |
|--------------|---------------|------|
| `auto_brief` | `auto_primary` | 仍是 `active`。高分、**行本身**是 RSS 一手官方源（`score.official_source=true`），且不是实操车道。`scripts/derive_briefs.py` 可以写成公开快讯 |
| `review` | `review_score` / `review_practice` / `review_no_primary` / `review_not_official` / `review_deferred` | 保持 `active` 或 `deferred`。`--write-review` 把清单写到私有池 `review/YYYY-MM-DD.md` |
| `drop` | `drop_low_score` | `status_in_pool=dropped`，`drop_reason=low_score`，`notes` 里留 `score:low_score value=…`。schema 要求这条 notes 非空 |

`review_not_official`：簇里有一手链接，但这一行自己不是 RSS 官方源。典型是 X 上的爆料帖和官方帖进了同一簇，或实验室自己的 X 账号。它们靠簇内印证拿到高分，但不会自动发布，必须人看。schema 用 `if band=auto_brief then official_source=true` 锁住这一条。

实操（`practice_handles`、`tier_prior=practice`、`lane_hint` 或 `participation=practice`）即使分高也是 `review_practice`，不会自动进快讯，也不会写 `public/practice/`。Magpie 这条车道仍然要人核过，`verified` 不由脚本改。

已经是 `editor_skip`、`promoted`、`rerouted`，或其它 `dropped` 的行不改状态、不覆盖原因。`low_score` 再跑 `annotate_gates` 也不会被抬回去。要重看，人先把原因改掉。

`pending` / `wrong_lane` / `quota` / `quota_defer` 仍然不是 `drop_reason`。

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

X 帖不会进自动档（`review_not_official`），所以 X 工作流通常只改私有池和审核清单。

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
python3 scripts/derive_briefs.py --self-check
python3 scripts/fetch_x_watch.py --self-check
python3 scripts/score_sources.py --self-check
python3 scripts/annotate_gates.py --self-check
python3 scripts/validate.py
```

`validate.py` 会把上面几项一并跑掉。没有 LLM 密钥时规则分必须能过。
