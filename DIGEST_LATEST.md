# AI Radar 主报 · 2026-10-16 08:00 北京时间

> 现行班次（Asia/Shanghai）：每天 08:00 主报；周一至周五 21:00 晚班。13:30 午间班已取消。

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html  
人读层：[表达规范 v0](docs/AIHOT对接与表达规范-v0.md)

睿，今天有一条必看。Meta 放出了可以下载的 Muse Spark Open。另外有一条画图工具可以关注。昨天的 Gemini 4 Argon 还在折扣期内。

## 今日必看

**Meta 放出 Muse Spark Open**

**是什么：** Meta 放出一份大模型。模型权重可以下载到自己的电脑或服务器上使用。

**要点：**
- 总参数 816B。每个词大约激活 42B。上下文最长 1M token。
- 它能读文字、图片、音频和视频，主打长程写代码和智能体任务。
- 权重可以在 Hugging Face 下载，也可以走 OpenRouter 这类托管接口。
- 许可可以免费用。大厂商卖接口要另议。它和上周的 Muse Wonder 不是一条线，Wonder 是闭源接口。Apple 演示过两台 Mac Studio 在本地跑，门槛高，别默认家里的电脑能跑。

**所以呢：** 如果你走开源或自己托管，或者怕闭源配额用完，这周用同一套长程写代码的题，把 Spark Open 的托管接口和你现在用的模型对打一遍。

**若证伪：** 如果独立评测显示，它在真实的长程写代码和智能体任务上稳定弱于同样成本的方案，或者托管价格用不起来，就收回「必须放进对照表」。

原文：https://research.meta.ai/blog/muse-spark-open

## 可关注

**Black Forest Labs 放出 FLUX.3 Image Klein**

**是什么：** 这是一套画图模型。权重可以下载到自己的电脑上使用。

**要点：**
- 发布当天就能在 Diffusers 里做文生图，也能用多张参考图。
- 提示词里可以用边界框控制画面布局。
- 蒸馏版默认 16 步。博客说在 H100 上大约 2 秒出一张 1024 像素的图。

**所以呢：** 如果你自己托管图床或封面，这周可以试一条。没有这个需求就先放着。

**若证伪：** 如果画质和可控性明显弱于你现在用的闭源画图模型，而且显存门槛太高，就先不跟。

原文：https://huggingface.co/blog/flux-3

归档在 `public/archive/2026-10-16.json`，本班 2 条。

## 还有效

**Google 向全球开放 Gemini 4 Argon**

**是什么：** Google 在 10 月 13 日向全球开放 Gemini 4 Argon。开发者和企业可以通过接口使用。

**要点：**
- 现在的导入价是每百万 token 输入 2 美元、输出 10 美元。
- 2026 年 11 月 30 日之后升到输入 4 美元、输出 20 美元。
- Google AI Ultra 可以用 Antigravity。Pro 和 Ultra 可以用 Gemini 应用，也可以用搜索里的 AI 模式。

**所以呢：** 折扣还在。这周用同一套长程任务，把 Argon 和你现在用的模型对打一遍。

**若证伪：** 如果独立评测显示，它在真实长程任务上稳定差于同样价位的 Sol 或 Opus，或者接口的配额和延迟用不起来，就收回「默认放进对照表」。

原文：https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-argon/

**Muse Wonder 仍是闭源接口**

**是什么：** 10 月 13 日的 Muse Wonder 和 Wonder Full 走闭源接口，也走 Muse Code。本班的 Spark Open 是可以下载的权重。两条线不要混在一起。

原文：https://about.fb.com/news/2026/10/introducing-muse-wonder-models/

## 附录

<details>
<summary>本班先不跟（12），这里只列 5 条</summary>

- Antigravity 向 Google AI Pro 打开了 Argon，并单独给了一周额度。这是已经在看的 Argon 怎么发放，不是新模型。先不跟一条新卡。
- ARC-AGI 公布了 Argon 的分数。这是已有条目的评测跟进。先不跟一条新卡。
- GPT-Live-1.1 更新了语音和口音。这是产品上的小改动，不是今天必须改的选型。先不跟。
- Opus 5.5 快速模式取消排队或加价。目前只有转述，没有 Anthropic 的官方原文。先当传闻，先不跟。
- Kling 4.0 目前只有转述，没有官方原文。先不跟。

其余 7 条同样先不跟，不写进正文。

</details>
