# 图谱活起来（C）

实战图谱不再把收藏比冻在 2026-10-20 的裸除法上。实操候选可以建议归入现有主题。人确认并且 `verified=true` 之后，才改手册或 `atlas.source.json`。不够「能照着做」的不上实操页：丢弃行（含 `practice_not_steps`）不进建议。不自动刮贴全文。不部署 Cloudflare Worker。

关注名单仍由人改。`practice_handles` 和 `a_tier` 不因收藏比升降。实操车道仍然不会 `auto_brief` 进快讯（B 已约定，这里不改）。

## 1. 主题建议怎么产生

脚本 `scripts/suggest_atlas_topics.py`。对照的是 `public/data/atlas.source.json` 里每个主题的 `tools`。命中工具名才建议主题。两个主题分数一样就留下人工指定，不猜。

公开实操（`practice.json`，以及还没并进它的 `practice/inbox`）都会进 `public/data/topic-suggestions.json`。理由只写主题和对上的工具名，不抄 `steps`。

私有池另算，可选。认这些字段，和仓里现有的一致：

| 信号 | 建议里的 `lane` |
|------|-----------------|
| `score.band_reason=review_practice` | `review_practice` |
| handle 在 `config.json` 的 `practice_handles` | `practice_handles` |
| `tier_prior=practice` | `tier_prior` |
| `lane_hint` 或 `participation=practice` | `lane_hint` |

`auto_brief`、`drop`、已丢弃、`prefilter=BLOCK` 不进建议。写出两处，都在私有池，不进 `public/`：

- 候选行上的 `atlas_suggestion`（`topic`、`reason`、`verified`、`apply`、`lane`）
- `suggestions/atlas-topics.jsonl`

`verified` 只在这条已经有一张公开实操卡、并且那张卡是 `verified=true` 时才为 true。池行自己不能把这个标成 true。

```bash
python3 scripts/suggest_atlas_topics.py --self-check
python3 scripts/suggest_atlas_topics.py
python3 scripts/suggest_atlas_topics.py --pool-dir ../ai-radar-pool
```

`apply` 三态：

| 值 | 含义 |
|----|------|
| `held` | 对上了主题，而且公开卡 `verified=true`。还要一份确认文件才会写图谱 |
| `blocked_unverified` | 对上了主题，但没验证。不写手册，页面上也不当成完备课程 |
| `no_topic` | 没对上，或两个主题打平。人指定 slug 之前不写 |

## 2. verified 怎么放行

确认文件不在仓库里。例如：

```json
{
  "items": [
    {
      "id": "prac-20261014-llm-file",
      "topic": "agent-skills",
      "verified": true,
      "playbook": {
        "title": "人写的一步",
        "detail": "人写的一句，不要整段粘贴 steps"
      }
    }
  ]
}
```

`playbook` 可以不写。不写时，只保证 `atlas.source.json` 里有这条 `origin=practice` 的来源，摘录用已经公开的 `takeaway`，不用 `steps`。写了 `playbook` 就多一句人写的手册，并引用这个 id。

下面任一情况都会拒绝，并且不改文件：

- 确认文件或实操卡有一边 `verified` 不是 true
- id 不在 `practice.json` / inbox（池里的候选要先由人写成公开实操卡）
- 主题 slug 不在图谱里
- 手册句整段包含某一步 `steps`（40 字以上）
- 链接不是 http(s)，或没有标题 / takeaway

脚本不改 `practice.json` 的 `verified`，不写 practice inbox，不写快讯。

```bash
python3 scripts/suggest_atlas_topics.py --apply confirm.json
python3 scripts/generate_derived.py
```

`--derive` 会在写入成功后接着跑派生。派生时，来源上的 `verified` 以 `practice.json` 为准。主题上 `unverified_practice > 0` 时，主题页写明「还不是完备课程」。

## 3. 需求信号怎么刷新

和 B 的 `smoothed_bookmark_like` 同一套常数（`config.json` 的 `score`）：

```text
每条有计数的原帖：(bookmarks + α) / (likes + β)
主题：把这些比值求平均，再按样本数向先验收缩
    (合计 + (α/β) × author_prior_n) / (条数 + author_prior_n)
```

当前 α=3，β=5，`author_prior_n`=3，先验是 0.6。一条都没有时不编一个比值。累计收藏仍是原始合计，收缩只作用在比值上。

计数从这几处取，同一条原帖留下 `observed_at` 更晚的那次。时间相同则保留已经滚过的结果，不用更旧的快照盖掉。对不上现有 source id 的链接不会新开一条素材。

| 输入 | 何时 |
|------|------|
| `atlas.source.json` 里已有的收藏和点赞 | 每次都读。观测时间用文件里的 `snapshot` |
| 上一次 `public/data/demand.json` | 文件已在就读，避免下次又退回快照 |
| `public/archive/` 里带 `engagement` 或 `likes`/`bookmarks` 的卡 | 每次都扫。现在的归档卡没有这些字段，所以不会改数；以后有了会接上 |
| 私有池候选的 `engagement` | 只有传了 `--pool-dir` |

写出的 `public/data/demand.json` 只有计数、时间和 `from`。没有正文，没有池状态。`watchlist` 固定是 `unchanged`。

```bash
python3 scripts/refresh_demand.py --self-check
python3 scripts/refresh_demand.py
python3 scripts/refresh_demand.py --pool-dir ../ai-radar-pool
python3 scripts/generate_derived.py
```

带了 `--pool-dir` 时，文件里 `pool_counts=true`。输出仍只有计数，可以提交。不要把池 JSONL 一起提交。

公开页（首页细字、主题卡、主题页）展示的是这次滚动的北京时间，以及平滑后的比值。没有更新的互动数时，页面会说明沿用的是图谱源里的计数。

## 工作流

编辑侧，需要更新图谱数字或建议时：

```bash
python3 scripts/suggest_atlas_topics.py
python3 scripts/refresh_demand.py
python3 scripts/generate_derived.py
python3 scripts/validate.py
```

人确认某条已验证实操可以进手册时，再加上 `--apply confirm.json`，然后重新跑派生和 `suggest_atlas_topics.py`（建议清单会回到 `held`，直到你再次确认）。

GitHub `schedule` 不会跑这两步。本仓不新增定时工作流，也不部署 Worker。若要用外部 cron 代为触发已经存在的入池工作流，调用方式仍在 [`score-and-briefs.md`](./score-and-briefs.md) 的「定时不准时」一节：`workflow_dispatch`，令牌 `GH_DISPATCH_TOKEN`。那个说明不包含本包的图谱刷新。

## 自检

```bash
python3 scripts/suggest_atlas_topics.py --self-check
python3 scripts/refresh_demand.py --self-check
python3 scripts/generate_derived.py
python3 scripts/validate.py
```

`validate.py` 会把上面两个自检一起跑，并核对：主题 `save_ratio` 等于这套平滑公式、`verified` 与 `practice.json` 一致、需求文件没有改名单、公开建议覆盖每张实操卡且未验证的不会标成可写。
