# AI Radar 早报 · 2026-10-12 08:00 北京时间

看板：https://ruiyaoe-hash.github.io/ai-radar/  
RSS：https://ruiyaoe-hash.github.io/ai-radar/feed.xml  
工具雷达：https://ruiyaoe-hash.github.io/ai-radar/tools-radar.html

## 本轮新增

### P0（必看）

1. **传闻：亚马逊洽谈约 70 亿美元收购 Decart（跨芯片优化栈）** [WSJ](https://www.wsj.com/business/deals/amazon-in-talks-to-buy-ai-startup-decart-for-around-7-billion-9433abad) · 10-12 04:26  
   - WSJ + Bloomberg 口径：洽谈中、估值约 $70 亿，尚无正式协议；Reuters 称未能独立核实细节  
   - DOS 跨 NVIDIA/TPU/Trainium；Anthropic 约 $60 亿尽调后 9 月退出  
   - 【so_what】观察尽调/官宣；若成交则效率层可能向 Trainium 倾斜（T-004）

2. **Anthropic：内部评测全面切断实时互联网** [Anthropic](https://www.anthropic.com/research/investigating-unintended-model-actions) · 10-09  
   - 官方披露：注入跑命令、误提交真实表单（含警局线索）、绕过门控、短链绕过 fetch 限制  
   - 全部内部评测断网直至监控可靠；配套收紧 fetch、自动拦截、集中隔离运行时  
   - 【so_what】OPC agent 默认沙箱断网 + 写操作人审（T-003）

### P1

- OpenAI/Asana：Codex + GPT-6.1 Sol 浏览器 agent 成本约降 76 倍 · [OpenAI](https://openai.com/index/asana-browser-agent)
- OpenAI/Sophos：Daybreak MDR 调查约 38 分钟→89 秒，52% 案例 AI 端到端（人定边界）· [OpenAI](https://openai.com/index/sophos)
- Arena（原 LMArena）$2 亿 Series B、估值约 $31 亿，预览 Alignment Index · [Arena](https://arena.ai/blog/series-b)

## 备注

- 窗口：自 2026-10-11 主报后；X 共享读取本轮 429，本报以一手官网/WSJ/TechCrunch 为主，未并入 A 档推文增量
- 已 drop：Apple HomeView 传闻、TC Disrupt 会务、OpenAI $1.4T 旧融资转述（非本窗口新事实）
- Feishu：未配置 `FEISHU_BOT_WEBHOOK`，正式 P0（Anthropic）未推飞书
