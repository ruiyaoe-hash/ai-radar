# X 入私有池（x pool ingest）

Phase 1/2 的班次操作。原始 X 抓取先全量入池（ingest all），再做门槛标注（annotate gates），最后才由编辑晋升。候选 JSONL 只进私有仓 `ruiyaoe-hash/ai-radar-pool` 的 `candidates/YYYY-MM-DD.jsonl`。公开仓不抓 X，也不存放这些文件。

字段、状态和真丢原因的契约在 `docs/candidate-pool.md`。RSS 那条管道、密钥 `AI_RADAR_POOL_TOKEN` 的权限和轮换在 `docs/rss-pool-ingest.md`。本文只写 X 班次怎么走，避免临场再发明路径。

## 班次

| 班次 | 钟点（Asia/Shanghai） | 谁抓 X |
|------|----------------------|--------|
| 早班 | 每天 08:00 | 当班 Alba |
| 晚班 | 工作日 21:00 | 当班 Alba |

公开 PR 的 CI 不抓 X。定时抓取在 `.github/workflows/ingest-x-pool.yml`：只有 Actions 密钥 `X_BEARER_TOKEN` 和 `AI_RADAR_POOL_TOKEN` 都在才请求 X API。缺密钥时工作流警告后成功退出。手灌 JSON 的路径保持不变，见下文。密钥就位后的打开方式和三档打分见 `docs/score-and-briefs.md`。

抓取文件只留在本机。不要提交到公开仓 `ai-radar`，也不要提交进私有池。

## JSON 怎么给 ingest_x

不要手写 JSONL。`scripts/ingest_x.py` 吃原始抓取，认这些形状：

| 形状 | 说明 |
|------|------|
| 顶层数组 | 每项一条帖子 |
| `items` / `posts` / `tweets` / `results` | 值为列表 |
| `data` | 列表。若是对象就当成单条。Twitter API v2 的 `includes.users` 用来把 `author_id` 对上 handle |
| 单条对象 | 身上有 `id`、`text` 或 `url` 之一 |

一条里会读的字段：

| 字段 | 写入 |
|------|------|
| `url` / `permalink` / `tweet_url` / `twitter_url` | 规范化后的 `url` / `url_norm`。`twitter.com` 和 `x.com` 收成同一个 status |
| `id` / `id_str` / `rest_id` / `tweet_id` | 数字 status id。有它时，候选 id（cid）用 `sha256("x-status:{id}")` 的前 12 位 |
| `text` / `full_text`，以及 `legacy.full_text` | `snippet`。这一步不判断 |
| `created_at` | `published_at`（ISO-8601 UTC，也认 Twitter 的英文时间串） |
| `handle` / `username` / `screen_name` / `author` / `user` | `source.handle`。去掉 `@`，转小写 |
| 整包的 `fetched_at` 或 `ingested_at` | 入库时间。没有就用当前时间。也可以用 `--ingested-at` 覆盖 |

没有 permalink、也没有数字 status id：不编造 URL，stderr 打一行 `FETCH_GAP`，进程以退出码 2 结束。其余条目照常写入。先拦再入库是禁止的。日后会被标成 BLOCK（拦截）的帖子，这一步也要落一行。

池文件名是 `ingested_at` 的北京日历日：`candidates/YYYY-MM-DD.jsonl`。cid 里的日期是 `published_at` 的北京日历日；没有发表时间就用 `ingested_at`。文件里已有的 `id` 不会被覆盖，所以重跑不会抹掉判断。

虚构例子（不是真实帖子）：

```json
{
  "fetched_at": "2026-10-15T00:05:00Z",
  "items": [
    {
      "id": "1001",
      "text": "FIXTURE sentence, not a real post.",
      "created_at": "2026-10-15T00:01:00Z",
      "username": "examplelab",
      "url": "https://x.com/examplelab/status/1001"
    }
  ]
}
```

## 检出私有池

仓库：`ruiyaoe-hash/ai-radar-pool`。检出放在公开仓**外面**，例如 `../ai-radar-pool`。不要放进公开仓目录里（包括 `public/`，也包括仓库根下的 `pool/`）。包装脚本会拒绝往公开仓里面写。

两条路用其一。令牌不入库，不要 echo，不要写进 `git remote` 的 URL。

### 路 A：本机 `gh` 已经能看见私有仓

`gh auth status` 里的账号对 `ruiyaoe-hash/ai-radar-pool` 有 Contents 读写时：

```bash
gh repo clone ruiyaoe-hash/ai-radar-pool ../ai-radar-pool
git -C ../ai-radar-pool pull --ff-only
```

已经克隆过就只跑 `pull`。

### 路 B：`AI_RADAR_POOL_TOKEN`

和 RSS 工作流同一枚密钥。细粒度 PAT，只给 `ai-radar-pool` 的 Contents 读写。怎么建、怎么轮换见 `docs/rss-pool-ingest.md`。不要把公开仓 `ai-radar` 勾进这枚令牌。

```bash
# 令牌已经在环境里。不要 echo。
GH_TOKEN="$AI_RADAR_POOL_TOKEN" gh repo clone ruiyaoe-hash/ai-radar-pool ../ai-radar-pool
git -C ../ai-radar-pool \
  -c "http.extraheader=AUTHORIZATION: bearer ${AI_RADAR_POOL_TOKEN}" \
  pull --ff-only
```

已经克隆过就只跑 `pull` 那一行。`http.extraheader` 只活在这一条命令里，不会写进 `.git/config`。

`repository not found` 或 API 404：当前身份看不见私有仓。换另一条路。这不是入池脚本坏了。不要把 `testdata/` 拷进私有仓当生产数据。

## 入池和门槛

在公开仓根目录：

```bash
python3 scripts/shift_ingest_x_to_pool.py \
  --fetch /绝对路径/fetch.json \
  --pool-dir ../ai-radar-pool
```

脚本只做两件事，都调用现成模块，不另写一套入池规则：

1. `ingest_x`：全量入池。`status_in_pool=pending`，判断字段为空。已有的 `id` 不覆盖。
2. `annotate_gates --only-pending`：只处理仍为 `pending` 且 `prefilter` 为空的行。不晋升，不打分，不写公开卡。打分是下一条命令，不在这个包装脚本里，避免重跑时改写已经标过的行。

可选参数都是 ISO-8601 UTC：

| 参数 | 作用 |
|------|------|
| `--ingested-at` | 覆盖入库时间。不传则用抓取包里的 `fetched_at` / `ingested_at`，再没有就用当前时间 |
| `--as-of` | 门槛的时效钟。不传则用当前时间 |

退出码：

| 码 | 含义 | 这一班怎么处理 |
|----|------|----------------|
| 0 | 每条都入池，门槛也跑完 | 可以提交私有池里的 `candidates/` |
| 2 | 有 `FETCH_GAP`。能识别的行已经写入，并且门槛已标完 | 可以提交已写入的行。先看 stderr，把缺身份的那几条补抓或记在班次笔记里 |
| 1 | 硬失败：JSON 打不开、解析失败、路径被拒绝、门槛脚本异常 | 不要提交。修好再跑。重跑是安全的：已有 `id` 不会被覆盖，已标过的行也不会被 `--only-pending` 改写 |

`set -e` 的 shell 会把退出码 2 也当成失败，从而挡住后面的提交。要接着走时，只在退出码为 1 时停下：

```bash
set +e
python3 scripts/shift_ingest_x_to_pool.py \
  --fetch /绝对路径/fetch.json \
  --pool-dir ../ai-radar-pool
code=$?
set -e
if [ "$code" -eq 1 ]; then
  echo "硬失败，不要提交私有池"
  exit 1
fi
```

`--pool-dir` 必须是私有仓根（它下面有 `candidates/`）。脚本在写文件之前拒绝两类路径：公开仓的 `public/`，以及公开仓检出内部的任何目录。

不调用飞书，不跑 derive，不改 Pages。

想对照脚本内部时，等价的两步是：

```bash
python3 scripts/ingest_x.py --input /绝对路径/fetch.json --pool-dir ../ai-radar-pool
python3 scripts/annotate_gates.py --pool-dir ../ai-radar-pool --only-pending
```

`ingest_x` 自己在有 `FETCH_GAP` 时也是退出码 2。包装脚本遇到这种情况仍会接着跑门槛，再把 2 交还给调用方。

门槛之后再打分（打分本身不写公开卡）：

```bash
python3 scripts/score_pool.py --pool-dir ../ai-radar-pool --as-of 2026-10-14T12:00:00Z --write-review
```

`--write-review` 把中高分和实操写进私有池 `review/YYYY-MM-DD.md`。低分留在池里，`drop_reason=low_score`。没有 LLM 密钥时这一步只跑规则分。

定时班次接着跑 `scripts/project_public_lanes.py --pool-dir …`。过了步骤门和收藏门的实操写入 `public/practice/inbox/`，分析行写入 `public/data/watch.json`，然后 `generate_derived.py` 并入页面。标题为空时用正文第一句做临时标题。没过门的不写公开卡。`verified` 不由脚本改成 true。

自检不访问网络，只用 `testdata/x-fetch/sample.json` 里的虚构句子：

```bash
python3 scripts/shift_ingest_x_to_pool.py --self-check
```

## 只提交私有池

公开仓这一班不要出现 `candidates/*.jsonl`。

```bash
cd ../ai-radar-pool
git add candidates
git diff --cached --name-only
```

`name-only` 里只能有 `candidates/` 下的文件。多出来的路径用 `git restore --staged -- <路径>` 拿掉，不要一起提交。

提交说明固定成这一句。日期是北京日历日。钟点只写当班的 `08:00` 或 `21:00`：

```text
ingest: X shift YYYY-MM-DD HH:mm Asia/Shanghai
```

例子：`ingest: X shift 2026-10-15 08:00 Asia/Shanghai`

没有 `candidates/` 的变更就不要空提交。说明里不要写令牌、抓取原文或公开仓路径。

推送：

```bash
# 路 A
git push origin HEAD

# 路 B（不要把令牌写进 remote）
git -c "http.extraheader=AUTHORIZATION: bearer ${AI_RADAR_POOL_TOKEN}" push origin HEAD
```

推的是私有仓。不要把这次提交推到公开仓 `ai-radar`。

## 晋升

门槛跑完、私有池那次 ingest 提交之后，Alba 再决定哪些 `active` 行进公开 `public/archive/`。脚本不代做这一步。

普通晋升（默认）：

- 公开卡写 `candidate_id`，值等于池行的 `id`（`cand-YYYYMMDD-` 加 12 位十六进制）
- 同一行池记录改成 `status_in_pool=promoted`，`archive_id` 写成那张公开卡的 `id`，`promotion_path=normal`
- 不要手改池行的 `id`
- 改池行的提交仍然只发生在私有仓，不要把 JSONL 带进公开仓的 digest 提交

紧急晋升（emergency，来不及先入池的例外，不是默认）：

- 公开卡写 `promotion_path=emergency`
- 可以没有 `candidate_id`，也可以没有池行

`config.json` 的 `pool_traceability_since` 现为 `2026-10-15`。北京日历日达到这一天的新归档卡，上面两条必须占一条。2026-10-14 及更早的卡不回填，也不要改已经发出的 digest。

`dropped` 不能晋升。`low_score` 也是真丢，notes 不能空。`deferred` 是延后，不是丢弃，留给后面的班次。编辑否决用 `editor_skip`，并且 `notes` 不能空。`pending`、`wrong_lane`、`quota`、`quota_defer` 都不是 `drop_reason`。

derive 只读公开归档和 practice inbox。Pages 只发布 `public/`。池 JSONL、弃稿和第三方全文都不进公开仓。

## 不在这一班做的事

- 不在公开 PR 的 CI 里抓 X。定时工作流见 `docs/score-and-briefs.md`；没配 `X_BEARER_TOKEN` 时它不请求 X
- 不把原始抓取 JSON、池 JSONL 或审核清单提交进公开仓
- 不改飞书、derive、Pages
- 不把真实帖子写进 `testdata/`
- RSS 第一批仍走原来的定时工作流，和这条 X 班次共用同一个私有池、同一枚 `AI_RADAR_POOL_TOKEN`
