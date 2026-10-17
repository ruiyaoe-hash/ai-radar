# RSS 入私有池（rss pool ingest）

Phase 4 只做第一批。公开仓提供脚本和信源表；候选 JSONL 只进私有仓 `ruiyaoe-hash/ai-radar-pool`。

## 拉哪些

`public/config/sources.json` 的 `fetch_batch`：

| 批 | 行为 |
|----|------|
| **1** | `scripts/ingest_rss.py` 会拉 `fetch_batch: 1` 的全部源。基线六个：`openai-blog`、`anthropic-news`、`deepmind-blog`、`huggingface-blog`、`gh-releases-openai`、`gh-releases-anthropic-sdk`；2026-10 扩容六个：`theverge-ai`、`qbitai`、`simonwillison`、`latent-space`、`import-ai`、`github-blog`。加源只改 `sources.json`，脚本不再维护 id 白名单 |
| **2** | 本阶段不拉。TechCrunch、HN、Reddit、Hugging Face trending、GitHub trending、arXiv、Product Hunt、融资汇总。`--batch 2` 直接拒绝 |

行和 `ingest_x` 同一套 schema：`channel=rss`，`status_in_pool=pending`，判断字段为空。工作流接着跑 `annotate_gates.py --only-pending`。不写公开 archive，不改 derive，不自动晋升。

定时是 UTC `30 0,6,12 * * *`，也就是北京时间 08:30、14:30、20:30，一天三次。另有 `workflow_dispatch`。这个工作流**不**在 pull request 上跑，所以公开 CI 不依赖私有仓，也不访问外网 feed。

feed 没有新条目时，日志写「无更新」。某一个源抓取失败会警告并继续；全部源都失败才让这一步变红。每个源一轮最多入库 `MAX_PER_SOURCE`（当前 10）条最新条目，防止全量存档型 feed 一次灌满池子。

## 密钥

名字：**`AI_RADAR_POOL_TOKEN`**

加在公开仓 `ruiyaoe-hash/ai-radar` 的 Settings → Secrets and variables → Actions。工作流只用它去检出并推送私有仓。公开仓这边的 job 权限是 `contents: read`，第一步 checkout 还关了 `persist-credentials`，避免这枚令牌碰到公开仓的 git remote。

### 建令牌

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens。

| 项 | 值 |
|----|----|
| Resource owner | `ruiyaoe-hash` |
| Repository access | **Only select repositories** → `ai-radar-pool` |
| Permissions | Contents: **Read and write**。其它保持 No access |
| 不要 | 不要把 `ai-radar`（公开仓）勾进同一枚令牌。不要给 Administration、Secrets、或全仓库的 Contents 写 |

私有仓的默认分支需要允许这枚令牌推 `candidates/`。如果 `main` 有分支保护，给这个身份开 bypass，或者改成往它有权限的分支推。不要为了省事改用仓库的 `GITHUB_TOKEN`：那个令牌看不到另一个私有仓。

### 轮换

1. 签发一枚新的 fine-grained token，范围仍只有 `ai-radar-pool` 的 Contents 读写。
2. 在公开仓 Actions secrets 里把 `AI_RADAR_POOL_TOKEN` 换成新值。
3. 撤销旧令牌。
4. 用 `workflow_dispatch` 跑一次 `Ingest RSS into private pool`。有新条目就会出现在私有仓的 `candidates/`；没有则日志是「无更新」。

令牌不入库。公开仓的 git 历史里不应该出现池 JSONL。

## 没配密钥时

工作流打 `::warning::`，说明密钥未配置，然后成功退出。公开的 validate / derive / Pages 不受影响。

本环境的云端令牌读 `https://github.com/ruiyaoe-hash/ai-radar-pool` 常是 404（`repository not found`）。那只说明当前身份看不见私有仓，不是脚本失败。有写权限的人按上面的空布局自己建仓即可，不要把 `testdata/` 拷进去当生产数据。

## 本地

```bash
python3 scripts/ingest_rss.py --self-check
python3 scripts/annotate_gates.py --self-check
python3 scripts/ingest_rss.py --pool-dir ../ai-radar-pool
python3 scripts/annotate_gates.py --pool-dir ../ai-radar-pool --only-pending
```

`--self-check` 只读 `testdata/rss/` 和 `testdata/gates/`，不访问网络。
