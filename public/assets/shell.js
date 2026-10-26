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

  // 主导航用任务名。品牌词「信号 / 造物 / 共鸣」留在随笔和视觉里，不放进这一排。
  const primary = [
    { href: "today.html", id: "today", label: "信息精选", hint: "按天回看选出来的几条", pages: ["today"] },
    { href: "briefs.html", id: "briefs", label: "信息简讯", hint: "按天回看事实简讯", pages: ["briefs", "week"] },
    { href: "tools-radar.html", id: "tools", label: "工具决策", hint: "推荐使用、值得关注", pages: ["tools"] },
    { href: "atlas.html", id: "atlas", label: "实战手册", hint: "把发现收成能照着做的方法", pages: ["atlas", "practice", "topic"] },
    { href: "observe.html", id: "observe", label: "专题观察", hint: "跟得更久的判断和随笔", pages: ["observe", "blog"] }
  ];

  function directLink(entry) {
    const safe = link(entry.href, false);
    if (!safe) return "";
    const on = entry.pages.indexOf(page) !== -1;
    const current = on ? ' aria-current="page"' : "";
    return `<li class="nav-slot${on ? " current" : ""}"><a class="nav-direct nav-trigger${on ? " current" : ""}" href="${esc(safe)}"${current} title="${esc(entry.hint)}">${entry.label}<small>${entry.hint}</small></a></li>`;
  }

  const more = {
    id: "more",
    zh: "更多",
    en: "More",
    pages: ["creators", "agent", "about"],
    items: [
      item("creators.html", "creators", "博主库", "实战手册里的作者索引"),
      item("practice.html", "practice", "做法条目", "能照着做的步骤全文"),
      item("blog/", "blog", "随笔", "编者写完才发的笔记"),
      item(FEISHU_GROUP, "feishu", "飞书订阅群", "每天推送到群里", true),
      item("agent.html", "agent", "给 Agent 用", "机器可读的数据入口"),
      item("atlas.html#method", "method", "收录标准", "什么能进主题手册"),
      item("about.html", "about", "这是什么", "站点定位与更正方式"),
      item(FEEDBACK_FORM, "feedback", "反馈 / 建议", "匿名问卷", true)
    ]
  };

  const moreOn = more.pages.indexOf(page) !== -1;
  const navHtml = primary.map(directLink).join("") + `<li class="nav-group${moreOn ? " current" : ""}" data-group="${more.id}">
        <button class="nav-trigger" type="button" aria-expanded="false" aria-controls="menu-${more.id}">${more.zh}<span class="en">${more.en}</span><span class="chev" aria-hidden="true"></span></button>
        <ul class="nav-menu" id="menu-${more.id}">${more.items.join("")}</ul>
      </li>`;

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
        <a class="btn btn-minimal btn-sub${page === "subscribe" ? " current" : ""}" href="${subscribe}"${page === "subscribe" ? ' aria-current="page"' : ""}>订阅更新</a>
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
    if (event.target.closest(".nav-menu a, a.nav-direct")) {
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
