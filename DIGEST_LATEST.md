# AI Radar 主报 · 2026-10-18 08:00 北京时间

> 现行班次（Asia/Shanghai）：每天 08:00 主报；周一至周五 21:00 晚班。13:30 午间班已取消。

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html  
人读层：[表达规范 v0](docs/AIHOT对接与表达规范-v0.md)

睿，主报有一条今日必看。DeepSeek 把 V4.1 Flash 更新到 1017。接口里的模型名不用改。同一天，搜索和抓取接口也开放了。

## 本班新增

**今日必看 · DeepSeek 更新 V4.1 Flash，并开放搜索接口**

**是什么：** DeepSeek 在 10 月 17 日把 V4.1 Flash 换成 DeepSeek-V4.1-Flash-1017。官网、手机应用和接口都已换上。模型权重可以下载到自己的电脑或服务器上使用。

**要点：**
- 接口模型名仍是 deepseek-flash，调用方式和价格都没有变。
- 不带工具的 HLE，上一版是 36.8，这一版是 42.6。Terminal-Bench 4.0，上一版是 31.2，这一版是 42.3。任务运行时间和输出长度都缩短了。
- 官方建议把 DeepSeek Harness（智能体编排）升到 0.2.1-rc.1 或更新。腾讯 CodeBuddy 和 WorkBuddy 也在适配名单里。
- 搜索和抓取接口每个每 1000 次调用 0.75 美元。经 DeepSeek Harness、Claude Code 和 Codex 的服务端工具，在 10 月 31 日 16:00（世界时）之前对接口用户免费。

**所以呢：** 这周不用改模型名。把 DeepSeek Harness 升到 0.2.1-rc.1 或更新，用你手头的写代码题目看完成时间和账单。要给智能体联网时，把搜索和抓取接口接上，赶在免费窗口结束前试一次。

**若证伪：** 如果同一套任务上，新版的完成时间或账单并没有好于上一版，或者搜索结果质量达不到能直接用，就收回「这周该升 Harness，并试用搜索接口」。

原文：https://api-docs.deepseek.com/zh-cn/updates/

## 今日仍有效

**Meta 放出 Muse Spark Open**（10-16 早报已上板）

**是什么：** Meta 放出一份大模型。模型权重可以下载到自己的电脑或服务器上使用。

**所以呢：** 本周用同一套长程写代码的题，把托管接口和你现在用的模型对打一遍即可。

原文：https://research.meta.ai/blog/muse-spark-open

**Google 向全球开放 Gemini 4 Argon**

**是什么：** Google 在 10 月开放 Gemini 4 Argon。开发者可以通过接口使用。导入折扣还在，11 月 30 日后涨价。

**所以呢：** 折扣期内仍建议同任务对照。

原文：https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-argon/

## 附录

<details>
<summary>本班先不跟（摘几条）</summary>

- WorkBuddy：只出现在 DeepSeek 的适配名单里。本班没有它单独的一手发布，不另开一条。
- RTX Spark 笔记本教程：外面精选站列了这一条。本班窗口里没有厂商一手主帖，先不跟。
- 其余 A 级账号在这个窗口里没有新的非回复帖。先不跟。

</details>
