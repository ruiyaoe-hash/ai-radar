# AI Radar 主报 · 2026-10-21 08:00 北京时间

> 现行班次（Asia/Shanghai）：每天 08:00 主报；周一至周五 21:00 晚班。13:30 午间班已取消。

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html  
人读层：[表达规范 v0](docs/AIHOT对接与表达规范-v0.md)

睿，主报没有新的「今日必看」。从昨晚 21:00 到今早这段窗口里，有一手官方发声（Mistral 语音套件、Perplexity 本机版），但都不改你今天本地智能体与主接口选型。本班不写填充卡。板上的 Muse Glimmer 30B、DeepSeek V4.1 Flash 1017、Muse Spark Open、Gemini 4 Argon 仍按原计划执行。

## 本班新增

无。今天的归档文件没有追加主报卡。

## 今日仍有效

**Meta 放出 Muse Glimmer 30B，可在消费级显卡上跑本地智能体**（10-20 早报已上板）

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

**Mistral 发布 Voxtral 3 语音套件与语音智能体接口**

**是什么：** Mistral 官方账号宣布 Voxtral 3：一套语音转写与语音合成模型，并配上语音智能体接口（voice agents API）。转写侧强调多语种、说话人分离和「说完再答」的回合检测；合成侧强调多语种表达力，并可通过标签控制情绪与语速。CEO Arthur Mensch 同步说，语音模型最好部署在推理模型附近。

**要点：** 这是一手官方发布，可信度够。Artificial Analysis（人工分析榜）随后把转写成绩摆进榜单前列，合成速度也标得很快。但它主攻的是「你要不要换一套语音进线」，不是「今天本地写代码智能体选哪套权重」。你这周动作仍是板上那四条；只有当你这周就要做语音助手或电话类智能体时，再把 Voxtral 3 放进对照。

原文：https://x.com/MistralAI/status/2112574615318876178

**Perplexity Computer 可在 Mac 上完全本机跑**

**是什么：** Perplexity CEO Aravind Srinivas 宣布，Perplexity Computer 现在可以在 Mac 上完全本机运行，不走云端推理，也可以断网用。

**要点：** 一手产品宣布。它和你板上的 Glimmer「自备权重跑本地智能体」不是同一条线：这边是厂商封装好的本机产品。你没有在用 Perplexity Computer 当主栈时，不必为它改今天选型；若你本来就在试它的 Mac 客户端，可以按官方说明打开本机模式看一眼隐私与离线可用性。

原文：https://x.com/AravSrinivas/status/2112583333825950207

**op7418：用 AI 改电视启动器界面（实操候选）**

**是什么：** 歸藏（op7418）参考两个流行项目，给自己做了一套电视启动器：只展示常用应用，并加了壁纸轮播；项目与参考链接写在帖里。

**要点：** 步骤感够，属实操车道，已进私有候选池。本班不自动全文上站。要上实操页，等你或编辑审过「能照着做」再晋升。

原文：https://x.com/op7418/status/2112574142562304491

**shao__meng：Flatkey 统一网关接多模态（实操候选）**

**是什么：** 邵萌（shao__meng）介绍 Flatkey：一个 Key（密钥）接入大量官方模型与工具接口，费用打进一份账单，并强调 CLI（命令行）接入适合给 Codex / Claude Code 挂图片、视频、音频模型。

**要点：** 实操向产品介绍，已进私有候选池。是否换网关要你自己审价格与稳定性；本班不上实操页。

原文：https://x.com/shao__meng/status/2112688351795138907

## 附录

<details>
<summary>本班先不跟（摘几条）</summary>

- Jim Fan 开源 Flora 机器人视觉数据引擎：一手开源，赛道偏机器人数据管线，不改你今天 OPC 主栈。
- OpenAI 收购 Orchestra Bio：生命科学运营软件，与你的本地智能体选型无关。
- Anthropic 蝎毒素蛋白设计科学博客：探索性实验，不是可试用工具发布。
- Simon Willison 用 Claude 做浏览器 RTS 游戏：演示帖，不是选型信号。
- ChatGPT「锁定聊天」、dotey 转述类产品更新：功能向，不单独改模型名或 Harness 计划。
- 外面精选站还列了 Modal Sticky Sessions、TorchTPU、Databricks MemCurrent 等；本班配置账号窗口里没有对应厂商一手主帖，或与你当前栈距离远，先不跟。

</details>
