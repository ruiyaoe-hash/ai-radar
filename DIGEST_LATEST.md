# AI Radar 晚班短报 · 2026-10-20 21:00 北京时间

> 现行班次（Asia/Shanghai）：每天 08:00 主报；周一至周五 21:00 晚班。13:30 午间班已取消。

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html  
人读层：[表达规范 v0](docs/AIHOT对接与表达规范-v0.md)

睿，晚班没有新的「今日必看」。中国白天加美东早晨这段窗口里，有一手官方开源（DeepSeek DeepInfer），但目标硬件是数据中心卡，不改你今天的本地智能体与接口选型。本班不写填充卡。早报板上的 Muse Glimmer 30B、DeepSeek V4.1 Flash 1017、Muse Spark Open、Gemini 4 Argon 仍按原计划执行。

## 晚班新增

无。今天的归档文件没有追加晚班卡。

## 今日仍有效

**Meta 放出 Muse Glimmer 30B，可在消费级显卡上跑本地智能体**（本早主报已上板）

**是什么：** Meta 发布约 300 亿参数、面向本地智能体任务的开放权重模型 Muse Glimmer（缪斯微光）。模型权重可以下载到自己的电脑或服务器上使用。许可是 Apache 2.0。4-bit 量化后语言部分大约 17GB，官方说可以塞进约 24GB 显存的设备。

**所以呢：** 这周若试本地智能体，先用 4-bit 包跑一小批带工具调用的任务，对照你现在用的同尺寸开源模型。它和 Muse Spark Open 不是同一条产品线：Spark 更大；Glimmer 专门压到消费级单卡。

**若证伪：** 如果同一套本地智能体任务上，它在完成率或速度上稳定弱于同尺寸、同显存预算的 Qwen 或 Gemma，或者 24GB 显存根本跑不起来，就收回「这周该把 Glimmer 放进本地智能体对照」。

原文：https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model  
权重：https://huggingface.co/meta-models/Muse-Glimmer-30B

**DeepSeek 更新 V4.1 Flash，并开放搜索接口**（10-18 早报已上板）

**是什么：** DeepSeek 在 10 月 17 日把 V4.1 Flash 换成 DeepSeek-V4.1-Flash-1017。官网、手机应用和接口都已换上。模型权重可以下载到自己的电脑或服务器上使用。同一天搜索和抓取接口也开放了。

**所以呢：** 这周不用改模型名。把 DeepSeek Harness（智能体编排）升到 0.2.1-rc.1 或更新，用你手头的写代码题目看完成时间和账单。要给智能体联网时，把搜索和抓取接口接上，赶在免费窗口结束前试一次。

**若证伪：** 如果同一套任务上，新版的完成时间或账单并没有好于上一版，或者搜索结果质量达不到能直接用，就收回「这周该升 Harness，并试用搜索接口」。

原文：https://api-docs.deepseek.com/zh-cn/updates/

**Meta 放出 Muse Spark Open**（10-16 早报已上板）

**是什么：** Meta 放出一份大模型。模型权重可以下载到自己的电脑或服务器上使用。

**所以呢：** 本周用同一套长程写代码的题，把托管接口和你现在用的模型对打一遍即可。更大、内存门槛更高的那条线；本地单卡智能体优先看早报的 Glimmer。

原文：https://research.meta.ai/blog/muse-spark-open

**Google 向全球开放 Gemini 4 Argon**

**是什么：** Google 在 10 月开放 Gemini 4 Argon。开发者可以通过接口使用。导入折扣还在，11 月 30 日后涨价。

**所以呢：** 折扣期内仍建议同任务对照。

原文：https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-argon/

## 可关注（未入今日必看）

**DeepSeek 开源 DeepInfer（深度推理）生产推理框架**

**是什么：** DeepSeek 官方账号宣布把线上支撑 DeepSeek-V4.1-Flash 的内部推理框架 DeepInfer 开源，许可是 Apache 2.0。同线程还开源了 deepseek-recipe（与官方接口对齐的编解码组件）。仓库地址：https://github.com/deepseek-ai/DeepInfer 。官方说明本次聚焦离线推理，栈基于 vLLM（开源推理服务），并借鉴 SGLang 与 TensorRT-LLM。公开资料写明目标硬件主要是 NVIDIA SM100 与华为 Ascend 950 一类数据中心加速器，不是消费级笔记本显卡。

**要点：** 这是一手官方帖，可信度够。但它改的是「自建生产级推理栈怎么跑」，不是「你今天选哪个聊天模型或本地智能体权重」。你这周的动作仍是早报那条：升 Harness、试用搜索接口、本地单卡优先试 Glimmer。只有当你要在机房或云上自建 DeepSeek 服务端时，再把 DeepInfer 放进对照。

原文：https://x.com/deepseek_ai/status/2112476496283775135  
仓库：https://github.com/deepseek-ai/DeepInfer

**vista8：内容发布工作流（飞书 → 博客 → 公众号 / X）**

**是什么：** 向阳乔木（vista8）分享一套内容发布链路：飞书写稿与点评，用 Skill（技能包）检查格式后发自己的博客，再从博客一键进公众号草稿箱；发 X 则用 Chrome 插件同步博客列表后选择发送。

**要点：** 步骤感清楚，属实操车道。已进私有候选池。要上实操页，等你或编辑审过「能照着做」并写进 practice inbox（实操收件箱）再晋升；本班不自动全文上站。

原文：https://x.com/vista8/status/2112436033690480918

**vista8：用 Codex 填 GEO 大会报备表**

**是什么：** 向阳乔木把营业执照、身份证、样例 PDF 放进一个文件夹，用提示词让 Codex（编程智能体）填深圳 GEO 大会审批报备资料，约十分钟完成。

**要点：** 实操向小例子，已进私有候选池。不单独改模型选型；审过后再考虑是否上实操页。

原文：https://x.com/vista8/status/2112449926336749923

## 附录

<details>
<summary>本班先不跟（摘几条）</summary>

- Artificial Analysis 上 Ming-3.0-tts 语音榜位次：评测机构信号，配置时间线里没有蚂蚁 / Ant Group 一手主帖，不以榜单单独升正式「今日必看」。
- Notion Business / Enterprise 的 AI 改为按月积分（11 月 2 日切换）：产品计费变更，不改你默认模型与本地智能体选型。
- Nathan Lambert 评论 DeepSeek 开源与联邦禁用的时机：观点帖，无可执行发布。
- Hugging Face 转发 Muse Spark 教程：转发，早报已有 Spark / Glimmer 正卡，不另开。
- Hailuo / MiniMax H3 社区成片与表情帖：产品宣传，不改选型。
- 邵盟转述斯坦福 CME 295、MIT harness 课、Meta Thin Orchestrator、Viggle JST-2 等：学习与转述向，留池。
- 归藏播客上榜、李继刚协作观感帖：内容 / 观点向，留池。
- 外面精选站还列了 llm-d 1.0（Kubernetes 原生分布式推理）等；本班不以对方榜单或未进配置时间线的二手单独入板。

</details>
