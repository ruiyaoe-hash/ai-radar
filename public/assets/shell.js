(function () {
  const page = document.documentElement.getAttribute("data-page") || "";
  const rootAttr = document.documentElement.getAttribute("data-root") || "./";
  const root = rootAttr.endsWith("/") ? rootAttr : rootAttr + "/";

  // 整站反馈问卷（匿名填写）。不是单卡投票，也不是飞书订阅群。
  const FEEDBACK_FORM = "https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd";
  // 飞书订阅群邀请。给人的零后端订阅路径，不是反馈问卷。
  const FEISHU_GROUP = "https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83";

  function esc(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function link(href, external) {
    const full = external ? href : root + href;
    return typeof window.safeHref === "function" ? window.safeHref(full) : "";
  }

  function item(href, id, label, hint, external) {
    const safe = link(href, external);
    if (!safe) return "";
    const on = !external && page === id;
    const cls = [on ? "active" : "", external ? "ext" : ""].filter(Boolean).join(" ");
    const current = on ? ' aria-current="page"' : "";
    const blank = external ? ' target="_blank" rel="noopener noreferrer"' : "";
    return `<li><a class="${cls}" href="${esc(safe)}"${current}${blank}>${label}<small>${hint}</small></a></li>`;
  }

  const groups = [
    {
      id: "signals", zh: "信号", en: "Signals",
      pages: ["today", "briefs", "week", "tools"],
      items: [
        item("today.html", "today", "今日必看", "当天最值得动手的信号"),
        item("briefs.html", "briefs", "快讯", "官方发布的短讯，自动更新"),
        item("week.html", "week", "本周归档", "按天翻看最近七天"),
        item("tools-radar.html", "tools", "可试用工具", "值得用上、可以试、先别跟")
      ]
    },
    {
      id: "creations", zh: "造物", en: "Creations",
      pages: ["atlas", "practice", "creators", "topic"],
      items: [
        item("atlas.html", "atlas", "实战图谱", "按场景整理的做法手册"),
        item("practice.html", "practice", "博主实操", "能照着做的教程与工作流"),
        item("creators.html", "creators", "博主库", "持续盯着的实操作者")
      ]
    },
    {
      id: "resonance", zh: "共鸣", en: "Resonance",
      pages: ["blog", "subscribe", "agent", "about"],
      items: [
        item("blog/", "blog", "随笔", "编者的长一点的想法"),
        item("subscribe.html", "subscribe", "订阅更新", "RSS 与按类订阅"),
        item(FEISHU_GROUP, "feishu", "飞书订阅群", "每天推送到群里", true),
        item("agent.html", "agent", "给 Agent 用", "机器可读的数据入口"),
        item("atlas.html#method", "method", "收录标准", "什么能进站、什么不收"),
        item("about.html", "about", "这是什么", "站点定位与更正方式"),
        item(FEEDBACK_FORM, "feedback", "反馈 / 建议", "匿名问卷", true)
      ]
    }
  ];

  const navHtml = groups.map((group) => {
    const current = group.pages.includes(page) ? " current" : "";
    return `<li class="nav-group${current}" data-group="${group.id}">
        <button class="nav-trigger" type="button" aria-expanded="false" aria-controls="menu-${group.id}">${group.zh}<span class="en">${group.en}</span><span class="chev" aria-hidden="true"></span></button>
        <ul class="nav-menu" id="menu-${group.id}">${group.items.join("")}</ul>
      </li>`;
  }).join("");

  const home = esc(link("index.html") || "./");
  const subscribe = esc(link("subscribe.html") || "./");

  const bar = `<a class="skip-link" href="#main">跳到正文</a>
  <header class="ember-top-bar">
    <div class="bar-inner">
      <a class="brand" href="${home}" aria-label="AI Radar 首页">
        <span class="ember-dot" id="radar-live" title="信号灯：最近 6 小时有更新时会呼吸" aria-hidden="true"></span>
        <span class="brand-name">AI Radar<span class="en">信号雷达</span></span>
      </a>
      <nav class="main-nav" id="site-nav" aria-label="主导航">
        <ul class="nav-groups">${navHtml}</ul>
      </nav>
      <div class="bar-actions">
        <a class="btn btn-minimal btn-sub" href="${subscribe}">订阅</a>
        <button class="menu-btn" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="打开导航"><span class="bars" aria-hidden="true"></span></button>
      </div>
    </div>
  </header>`;

  const self = document.currentScript;
  if (self) self.insertAdjacentHTML("beforebegin", bar);

  const nav = document.getElementById("site-nav");
  const menuBtn = document.querySelector(".menu-btn");

  function closeGroups(except) {
    document.querySelectorAll(".nav-group.open").forEach((el) => {
      if (el === except) return;
      el.classList.remove("open");
      const trigger = el.querySelector(".nav-trigger");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    });
  }
  function setSheet(open) {
    if (!nav || !menuBtn) return;
    nav.classList.toggle("open", open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    menuBtn.setAttribute("aria-label", open ? "关闭导航" : "打开导航");
    document.body.classList.toggle("nav-locked", open);
  }
  function closeAll() {
    closeGroups(null);
    setSheet(false);
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest(".nav-trigger");
    if (trigger) {
      const group = trigger.closest(".nav-group");
      const open = !group.classList.contains("open");
      closeGroups(group);
      group.classList.toggle("open", open);
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    if (event.target.closest(".menu-btn")) {
      setSheet(!nav.classList.contains("open"));
      return;
    }
    if (event.target.closest(".nav-menu a")) {
      closeAll();
      return;
    }
    if (!event.target.closest(".nav-group")) closeGroups(null);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const hadOpen = document.querySelector(".nav-group.open, .main-nav.open");
    closeAll();
    if (hadOpen && menuBtn && window.getComputedStyle(menuBtn).display !== "none") menuBtn.focus();
  });
  window.RadarShell = { open: () => setSheet(true), close: closeAll };

  // 信号灯只看两份公开数据的顶层 updated（「YYYY-MM-DD HH:mm 北京时间」）：
  // briefs.json（快讯）与 items.json（看板）。取较新的一个。
  // 距现在不超过 6 小时 → is-live（琥珀色呼吸）；更久，或读不到时间 → is-idle（静止灰点）。
  const LIVE_MS = 6 * 60 * 60 * 1000;
  function parseUpdated(text) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(text || ""));
    if (!m) return 0;
    return Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00+08:00`) || 0;
  }
  function checkLive() {
    const dot = document.getElementById("radar-live");
    if (!dot || typeof fetch !== "function") return;
    const read = (name) => fetch(root + name, { cache: "no-cache" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => parseUpdated(data && data.updated))
      .catch(() => 0);
    Promise.all([read("briefs.json"), read("items.json")]).then((stamps) => {
      const latest = Math.max(...stamps);
      const live = latest > 0 && Date.now() - latest <= LIVE_MS;
      dot.classList.remove("is-live", "is-idle", "live", "idle");
      dot.classList.add(live ? "is-live" : "is-idle");
      const at = latest > 0
        ? new Date(latest).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
        : "";
      if (at) dot.title = live ? `最近更新 ${at}（北京时间）` : `上次更新 ${at}（北京时间），信号灯暂歇`;
      document.dispatchEvent(new CustomEvent("radar:live", { detail: { live, at } }));
    });
  }

  // Cloudflare Web Analytics。token 必须与这段片段一致，不要改。
  // 在 DOMContentLoaded 时追加到 body 末尾，这样每个加载 shell 的页面都会在 </body> 前带上 beacon。
  const CF_BEACON_SNIPPET = `<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "964a2081359a4ef8aa36617df12bae1f"}'></script><!-- End Cloudflare Web Analytics -->`;

  function installCfBeacon() {
    if (!document.body || document.querySelector("script[data-cf-beacon]")) return;
    const holder = document.createElement("template");
    holder.innerHTML = CF_BEACON_SNIPPET;
    const parsed = holder.content.querySelector("script");
    if (!parsed) return;
    const script = document.createElement("script");
    for (const name of ["type", "src", "data-cf-beacon"]) {
      const value = parsed.getAttribute(name);
      if (value) script.setAttribute(name, value);
    }
    document.body.appendChild(script);
  }
  function onReady() {
    installCfBeacon();
    checkLive();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
