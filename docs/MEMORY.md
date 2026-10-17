# AI Radar × Alba 协作 Memory（有价值产出与约定）

> 覆盖范围：睿（yao rui）与 Alba 从首次对话至 **2026-10-17**（Asia/Shanghai）的聊天与通话沉淀。  
> 用途：给人与后续 Agent 快速对齐「已做成什么、定了什么、不要推翻什么」。  
> 非机密：可进公开仓；**不含** webhook 密钥、token、私有池原文。

---

## 1. 角色与协作约定

| 项 | 约定 |
|---|---|
| Alba 定位 | AI OPC（一人公司）创业搭档：全球信号官 + AI 产品/技术/市场教练官；优先可下手方向与刻意练功 |
| 称呼 | 用户称「睿」；助手称「Alba」 |
| 沟通 | 先结论；精准不糊弄；简洁通俗（编程小白友好）；英文术语后紧跟中文括号注解（对话交付） |
| 附加职责 | **需求表达训练师**：每次需求可先执行，再补一句可改写的教练点评 |
| 复盘 | 周报周日约 09:00（Asia/Shanghai）；另有月/季/年报例程；复盘落在对话，不替睿发明选题 |
| 写作管道 | **不**主动跑比特涅槃/选题会/写作管道，除非当轮明确要求 |
| Bot 策略 | 默认一个持久 Alba（OPC 总调度）；仅在长期记忆/人格隔离、重活并行、权限隔离时才拆 Bot |
| 关键命名 | 须睿拍板 |

睿简档（公开可知）：写作/IP「时初白」，公众号「比特涅槃」；正职养家不可裸辞；副业做 AI 内容与一人事业验证；Gmail `ruiyaoe@gmail.com`；时区 Asia/Shanghai。

---

## 2. AI Radar：产品定位与站点

| 项 | 内容 |
|---|---|
| 站点 | https://ruiyaoe-hash.github.io/ai-radar/ |
| 公开仓 | https://github.com/ruiyaoe-hash/ai-radar （public） |
| 私有候选池 | https://github.com/ruiyaoe-hash/ai-radar-pool （PRIVATE） |
| North Star | 可行动信号数（卡片动作：tried / thesis_updated / shared / ignored） |
| 定位 | 决策信号系统：事件卡 + 结构化 so_what（含 falsifier、thesis_id）+ theses；镜头=工具/赛道/模式/时机 |
| 品牌 | 侧栏「比特涅槃 / Bit Nirvana」logo（二进制环+烟）；字标黑客风频谱（等宽 + 波形 + 扫描线，青绿霓虹）；**不抄 AIHOT** |
| 部署 | GitHub Pages = Actions 部署 `public/`（build_type=workflow）；根目录遗留镜像可退休 |

### UI 标签（2026-10-13 定稿）

- **决策权重**：全部 / 今日必看 / 市场信号 / 重点关注（对应 P0 / P0-待证 / P1）
- **内容镜头**：不限 / 试用工具 / 行业动态 / 方法模式 / 时机窗口（对应 lens 工具/赛道/模式/时机）
- **栏目**：含「博主实操」（头部博主最新有价值的 AI 工具用法/创意/变现）

### 反馈与订阅（2026-10-13 定稿方向）

- 交互：有用 / 没用 / 有误·漏报；**早期不公开展示计数**
- 否决：飞书 webhook 写票、每次投票热写 git
- 第 0 步：零后端（侧栏飞书问卷 + 订阅群）+ 无 cookie 统计事件验证参与率；达标后再 Worker + D1 热存储 + 每日快照回仓
- 反馈进信源记分与更正闭环；订阅仍用飞书群
- 问卷：https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd
- 订阅群：https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83
- Cloudflare Web Analytics：hostname=`ruiyaoe-hash.github.io`（只做浏览量，不做卡片赞踩）

---

## 3. 班次与例程（Asia/Shanghai）

| 班次 | 时间 | 状态 |
|---|---|---|
| 主报 | 每天约 **08:00** | 启用（例程 `AI Radar 主报`） |
| 晚班 | **周一至周五约 21:00** | 启用（例程 `AI Radar 晚班`） |
| 午间班 | 原 13:30 | **已取消**（Phase 0） |

主报/晚班例程已写入「表达规范 v0」；班次会走 X→`ingest_x`（PR #14 已合）。

其他协作例程：沟通复盘周/月/季/年；飞书入站 webhook。

---

## 4. 架构与安全（已落地要点）

| 主题 | 决策 |
|---|---|
| 公私分离 | 公开仓：schema、人读层、配置名单、派生静态页；私有池：抓取原文与候选；**名单公开，原文不进公开仓** |
| 写入分工 | `ingest_x` 等确定性写入；Alba 只补判断字段；GitHub Actions 负责 schema CI / derive / deploy-pages |
| 今日精选坑位 | 决策 / 工具 / 实操（各一） |
| Agent 接入路径 | ① 文档 + 静态 JSON/RSS/Schema/`llms.txt` → ② Skill → ③ MCP（逐步） |
| 提示词注入 | validate + Schema 限长 + 公开面禁止/剥离原文；SECURITY 补强（相关 PR 已合） |
| Agent 页 | 给人读也通顺，但文案只说「给 Agent 用、怎么取」；不写「人也读」 |

---

## 5. 表达规范：「中文用户思维表达」

跨项目 skill（本地 skill id：`skill-1792157017823`）。站点文案已按此改写，**PR #19 已合入 main**（约 2026-10-16/17）。

### 铁律摘要

1. **用户思维 ×3**：第一次进站零背景——看得懂？知道价值？知道下一步？
2. 每段写清：**是什么 / 价值 / 下一步**；完整句子；通俗 ≠ 省略关键信息。
3. **禁止「不是什么」** 否定对照；背景知识指导写法，不写进文案。
4. 整页单内容可用「本页」；一页多板块用「该板块」。
5. 勿把「纯文本」等格式标签当卖点。
6. Top3 / 今日精选：**「从全部信息里精选的最重要 3 条——时间紧只看这 3 条就够」**；禁止「今天先做这 3 件」。
7. Agent 索引：是什么、有用、怎么取；人话。
8. 语感：像人口述，少碎句号、少海报对仗、少英文 bullet 硬切。

睿反馈：写中文内容时可优先用 Claude（Opus 首选）辅助语序。

---

## 6. 关键已合 PR 里程碑（公开仓）

不完全列举，便于回溯：

| PR | 主题 |
|---|---|
| #3–#10 一带 | 信源、班次字段、安全、反馈侧栏、飞书群、Analytics、根镜像退休等 |
| #14 | 班次接入 X→`ingest_x` |
| #15 | 公开仓人读层 / 表达规范 v0 |
| #16 | Agent 第①步：Schema、`llms.txt`、agent 页 |
| #17 一带 | 提示词注入防护 |
| #18 | agent.html 人读友好 |
| #19 | 全站中文文案按「中文用户思维表达」改写（含「今日精选」等） |

站点曾短暂滞后旧文案「今天先做这 3 件」；合入后以 Actions 部署为准。

---

## 7. 当前监测信源（公开）

**结论：名单公开。** 任何人可读 `public/config/sources.json` 与根目录 `config.json`（`a_tier` / `practice_handles`）。公开的是「盯谁」，不是抓到的原文。

### 7.1 一手 RSS / 发布源（`fetch_batch=1`，会入池）— 6 个

| id | 名称 | 类型 |
|---|---|---|
| openai-blog | OpenAI Blog | rss |
| anthropic-news | Anthropic News | rss |
| deepmind-blog | Google DeepMind Blog | rss |
| huggingface-blog | Hugging Face Blog | rss |
| gh-releases-openai | OpenAI GitHub Releases | github_releases |
| gh-releases-anthropic-sdk | Anthropic SDK Releases | github_releases |

### 7.2 已登记、本阶段不抓（`fetch_batch=2`）— 10 个

arXiv cs.AI、TechCrunch AI、HN 过滤 AI、Show HN AI、r/LocalLLaMA、HF Trending、Product Hunt AI、融资 Google News RSS、GitHub trending Python/TS daily。

### 7.3 X · A 级（`a_tier`）— 30 个

`@karpathy` `@gdb` `@markchen90` `@ilyasut` `@geoffreyhinton` `@JeffDean` `@demishassabis` `@drfeifei` `@DrJimFan` `@fchollet` `@natolambert` `@polynoamial` `@OpenAI` `@AnthropicAI` `@GoogleDeepMind` `@AIatMeta` `@deepseek_ai` `@Alibaba_Qwen` `@MistralAI` `@_akhaliq` `@huggingface` `@ArtificialAnlys` `@arcprize` `@lmarena_ai` `@dotey` `@shao__meng` `@dongxi_nlp` `@simonw` `@sama` `@clementdelangue`

### 7.4 X · 实操（`practice_handles`）— 8 个

`@op7418` `@vista8` `@lijigang` `@bcherny` `@trq212` `@mattpocockuk` `@addyosmani` `@ryolu_`

名义总监测点约 **54**（不重复计 id）。

---

## 8. AIHOT 对照（2026-10-17 OSINT）

| 项 | 结论 |
|---|---|
| 官网 | https://aihot.news（legacy `aihot.virxact.com` 将于 2026-10-31 退役） |
| 声称监测 | **899** = X 523 · RSS 184 · 网页 145 · 公众号 23 · 接口 24 |
| 完整名单 | **不公开**；在飞书登录墙后的 `/admin/sources` |
| 公开仓 | https://github.com/KKKKhazix/AIHOT — `industry/sources.json` 仅 **18 条演示种子**，非生产 |
| `/api/v1/sources` | **404**；OpenAPI 无 sources 路径 |
| 可重建 | About SSR `sampleSources` + 公开 API 近 7 天条目等 → **约 415/899（~46%）** |

### 对 AI Radar「值得补盯」优先建议（尚未写入仓库，待睿确认再 PR）

一手厂商 / 工程博客：

- Google Blog：AI / Google Developers Blog  
- Meta Newsroom · AI、Meta Engineering  
- NVIDIA Blog / Newsroom / Technical Blog  
- Microsoft Research / Official Blog  
- Apple Machine Learning Research  
- Qwen Blog、Cursor Blog、Sam Altman Blog  

高杠杆作者 / 工程（RSS 补 X 之外长文）：

- Nathan Lambert · Interconnects（X 已有 `@natolambert`，缺 RSS）  
- Ethan Mollick · One Useful Thing  
- LangChain Blog、vLLM、Together AI、OpenHands  

可补 X（当前 `a_tier` 没有）：`@GeminiApp` `@MetaNewsroom` `@TencentHunyuan` `@Hailuo_AI` `@AravSrinivas` `@arthurmensch`

**暂不硬跟：** 大量 heat_signal 消费科技媒体、AIHOT 那 23 个公众号（抓取贵、噪声大，与「少而准」不合）。

---

## 9. 其他有价值约定 / 偏好

- **少而准** 信源策略：优先一手厂商与高杠杆作者；不全量追热度榜。
- 睿自称编程小白：讲 Git/CI/工程概念时结合 AI Radar 场景、小白友好。
- 本地工作区：`D:\Xspace`（统一工作台，git 本地不主动 push）；配对 `D:\my-wiki`；「自我迭代」私密。
- 飞书 Alba 桥：入站例程已建；PC 关机桥可仍在线（视部署机）；曾出现午夜长连接僵尸态，需健康检查/重启意识。
- Agent-Ready 硬件与高效用 AI 习惯（播客沉淀）：入口/出口钩子而非完整 Agent；files-as-memory；多工具分工；最短可行实现；开放接口；有意识沙箱。
- 中国封闭平台 vs 开放 RSS：公众号等人读 + blog/RSS 给 Agent 的双轨，适用于比特涅槃，但 **不主动** 开选题管道。

---

## 10. 待办 / 开口等待睿确认（截至 2026-10-17）

- [ ] 是否按 §8 优先名单改 `sources.json` / `a_tier` 开一版信源 PR  
- [ ] Agent 接入第②步 Skill、第③步 MCP（第①步已落地）  
- [ ] 反馈参与率达标后的 Worker+D1 热存储  

---

## 11. 维护说明

- 有新的定稿决策、合入 PR、信源批次变更时，**追加本节日期条目或改对应章节**，勿静默覆盖关键数字。  
- 密钥与私有池路径细节只写在私密笔记 / secrets，不进本文件。  
- 生成日：2026-10-17 Asia/Shanghai · 整理：Alba（电话口述需求）

