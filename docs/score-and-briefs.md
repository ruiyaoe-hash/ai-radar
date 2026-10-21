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
| `prior` | `tier_mix` × 档位权重 + (1−tier_mix) × 平滑命中率。档位来自 `tier_prior` / `role_guess`（T1、a_tier 高，T3 低，名单外 0.48）。命中率 = `(promoted条数 + hit_alpha) / (promoted + dropped + hit_alpha + hit_beta)`。**丢弃行在分母里**。还没决定的 `active` 不进分子也不进分母 |
| `decay` | 发表时间到 `--as-of` 的小时数。没有 `published_at` 时固定 0.55，不用入库时间假装很新 |
| `corroboration` | 同簇里 `prefilter=PASS` 的独立 handle（或无 handle 时的 URL）数，每多一个 +0.08，最多三个；簇内有一手/官方链接再 +0.16。底是 0.72，上限 1 |
| `velocity` | 没有收藏/点赞计数时为 1（RSS 不因此吃亏）。有计数时，`(bookmarks+bookmark_prior)/(likes+like_prior)` 和每小时收藏速度都按该作者在池里的样本归一，样本少时向先验收缩（`author_prior_n`）。丢弃行的计数也进基线 |
| `actionability` | 规则：步骤词、命令行、GitHub/GitLab 仓库链接。上限 `actionability_cap`。不是模型判分 |

默认常数在 `config.json` 的 `score`。当前 τ=36 小时，自动档 ≥ 0.52，人工档 ≥ 0.34。

## 三档

| `score.band` | `band_reason` | 池内 |
|--------------|---------------|------|
| `auto_brief` | `auto_primary` | 仍是 `active`。高分、簇内有一手，且不是实操车道。`scripts/derive_briefs.py` 可以写成公开快讯 |
| `review` | `review_score` / `review_practice` / `review_no_primary` / `review_deferred` | 保持 `active` 或 `deferred`。`--write-review` 把清单写到私有池 `review/YYYY-MM-DD.md` |
| `drop` | `drop_low_score` | `status_in_pool=dropped`，`drop_reason=low_score`，`notes` 里留 `score:low_score value=…`。schema 要求这条 notes 非空 |

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

`config.json` 里「按 bookmark 与 bookmark÷like 升降」指的是这个比值会进入候选 `velocity`，以及信源榜上的 `bookmark_like_ratio`。本包不自动改 `a_tier` / `practice_handles` 名单，也不滚动图谱手册里的收藏快照。

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
- 每轮最多 20 条自动档
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

抓取脚本把 X API v2 的用户时间线收成 `ingest_x` 已经认识的 JSON（含 `public_metrics`）。令牌不入库、不打印。原始抓取文件不要提交。

工作流在推私有池之前跑 `scripts/pool_git_push.sh`：`git pull --rebase` 失败会重试，避免和 RSS 工作流同时写 `candidates/`。公开仓这次只可能多一个 `public/briefs.json` 提交，用的是仓库自己的 `GITHUB_TOKEN`，不是池令牌。

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
