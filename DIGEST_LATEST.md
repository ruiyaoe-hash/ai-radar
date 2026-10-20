# AI Radar 主报 · 2026-10-20 08:00 北京时间

> 现行班次（Asia/Shanghai）：每天 08:00 主报；周一至周五 21:00 晚班。13:30 午间班已取消。

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html  
人读层：[表达规范 v0](docs/AIHOT对接与表达规范-v0.md)

睿，主报有一条「今日必看」：Meta 放出 Muse Glimmer 30B。如果你这周要在自己电脑上跑本地智能体，而不只靠云端接口，把它放进同尺寸对照。DeepSeek V4.1 Flash 1017、Muse Spark Open、Gemini 4 Argon 仍按原计划执行。

## 本班新增

**Meta 放出 Muse Glimmer 30B，可在消费级显卡上跑本地智能体**

**是什么：** Meta 发布约 300 亿参数、面向本地智能体任务的开放权重模型 Muse Glimmer。模型权重可以下载到自己的电脑或服务器上使用。许可是 Apache 2.0。官方目标是在一台 Mac 或带单块消费级显卡的个人电脑上跑通多步推理、工具调用和失败重试。4-bit 量化后语言部分大约 17GB，官方说可以塞进约 24GB 显存的设备。

**要点：** 同尺寸对照里，官方点名工具使用和智能体完成度优于 Qwen3.6-27B 与 Gemma4-31B。权重在 Hugging Face 可下，并带 GGUF 量化包和 DFlash 推测解码草稿模型。

**所以呢：** 它和已经上板的 Muse Spark Open 不是同一条产品线。Spark 更大、偏托管或高端本机；Glimmer 专门压到消费级单卡。这周若试本地智能体，先用 4-bit 包跑一小批带工具调用的任务，对照你现在用的同尺寸开源模型。

**若证伪：** 如果同一套本地智能体任务上，它在完成率或速度上稳定弱于同尺寸、同显存预算的 Qwen 或 Gemma，或者 24GB 显存根本跑不起来，就收回「这周该把 Glimmer 放进本地智能体对照」。

原文：https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model  
权重：https://huggingface.co/meta-models/Muse-Glimmer-30B  
X：https://x.com/AIatMeta/status/2112265822274302066

## 今日仍有效

**DeepSeek 更新 V4.1 Flash，并开放搜索接口**（10-18 早报已上板）

**是什么：** DeepSeek 在 10 月 17 日把 V4.1 Flash 换成 DeepSeek-V4.1-Flash-1017。官网、手机应用和接口都已换上。模型权重可以下载到自己的电脑或服务器上使用。同一天搜索和抓取接口也开放了。

**所以呢：** 这周不用改模型名。把 DeepSeek Harness（智能体编排）升到 0.2.1-rc.1 或更新，用你手头的写代码题目看完成时间和账单。要给智能体联网时，把搜索和抓取接口接上，赶在免费窗口结束前试一次。

**若证伪：** 如果同一套任务上，新版的完成时间或账单并没有好于上一版，或者搜索结果质量达不到能直接用，就收回「这周该升 Harness，并试用搜索接口」。

原文：https://api-docs.deepseek.com/zh-cn/updates/

**Meta 放出 Muse Spark Open**（10-16 早报已上板）

**是什么：** Meta 放出一份大模型。模型权重可以下载到自己的电脑或服务器上使用。

**所以呢：** 本周用同一套长程写代码的题，把托管接口和你现在用的模型对打一遍即可。更大、内存门槛更高的那条线；本地单卡智能体优先看本班新增的 Glimmer。

原文：https://research.meta.ai/blog/muse-spark-open

**Google 向全球开放 Gemini 4 Argon**

**是什么：** Google 在 10 月开放 Gemini 4 Argon。开发者可以通过接口使用。导入折扣还在，11 月 30 日后涨价。

**所以呢：** 折扣期内仍建议同任务对照。

原文：https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-argon/

## 可关注（未入今日必看）

**OpenAI：低资源编程语言上的构建与迁移能力**

**是什么：** OpenAI 官方称最新模型在 COBOL、Fortran、Visual Basic 等低资源编程语言上的构建与迁移能力有提升，并配套评测。

**要点：** 一手官方帖。除非你这周在做银行或政府类遗留系统迁移，否则不改今天的通用模型与工具选型。

原文：https://x.com/OpenAI/status/2112310345863930168

**Artificial Analysis：HealthBench 榜与 FLUX 3 Max 视频位次**

**是什么：** Artificial Analysis 上线了 HealthBench / HealthBench Professional 榜，并转述 fal 与 Black Forest Labs 的 FLUX 3 Max 在 AA-Video 榜上的位次。

**要点：** 这是评测机构与媒体向信号。HealthBench 加固对医疗对话评测的对照，不单独改你的默认模型。FLUX 3 Max 本班配置账号时间线里没有 fal / Black Forest Labs 一手主帖，不以评测榜单独升正式「今日必看」。

HealthBench 帖：https://x.com/ArtificialAnlys/status/2112318755321868493  
FLUX 3 Max 帖：https://x.com/ArtificialAnlys/status/2112266414593827110

**vista8：乔木剪藏插件更新（Markdown 编辑器 + 发 X 文章）**

**是什么：** 向阳乔木（vista8）更新 qiaomu clipper 插件，加了所见即所得 Markdown 编辑器和 ChatGPT 登录后一键发 X 文章；并称下一版会去掉视频下载以免合规风险。

**要点：** 实操车道优先进私有候选池。要上实操页，等你或编辑审过「能照着做」再晋升；本班不自动全文上站。

原文：https://x.com/vista8/status/2112170563997516076

## 附录

<details>
<summary>本班先不跟（摘几条）</summary>

- The Information 传闻 Anthropic 新模型「话说一半也能猜意图」：单源媒体传闻，最高只能待证，不进今日必看。
- ARC Prize 公布 Reflection Beam 1.0 在 ARC-AGI 上的成绩：评测增量，不改今天接口或本地模型选型。
- Gemini 应用演示用 Gemini 4 Argon 做 3D Wizard Chess：产品演示，已在板上的 Argon 不另开卡。
- ChatGPT Slides 加多人协作：产品功能增量，不改模型选型。
- 外面精选站还列了美国国土安全部要求联邦机构移除 DeepSeek、Inception Mercury 3 上 OpenRouter、Arena 上 DeepSeek Flash 开源第一等；本班不以对方榜单或未进配置时间线的二手单独入板。

</details>
