(function () {
  const page = document.documentElement.getAttribute("data-page") || "";
  const icons = {
    bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/></svg>',
    list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/></svg>',
    grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    rss: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.5" fill="currentColor" stroke="none"/></svg>',
    agent: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/><path d="M19 8v4M17 10h4"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M12 10v6M12 7h.01"/></svg>'
  };

  // 飞书订阅群邀请。给人的零后端订阅路径。legacy 根页面不加载 safe-href.js，这里只放固定 https。
  const FEISHU_GROUP = "https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83";

  function item(href, id, label, icon, external) {
    const safe = typeof window.safeHref === "function" ? window.safeHref(href) : href;
    if (!safe) return "";
    const hrefAttr = String(safe).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    const active = !external && page === id ? " active" : "";
    const current = !external && page === id ? ' aria-current="page"' : "";
    const blank = external ? ' target="_blank" rel="noopener noreferrer"' : "";
    return `<a class="${active.trim()}" href="${hrefAttr}"${current}${blank}><span class="ico" aria-hidden="true">${icons[icon]}</span>${label}</a>`;
  }

  const spec = `<svg class="wm-spec" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden="true">
    <polyline fill="none" stroke="#2dd4bf" stroke-width="1.2" stroke-linejoin="round"
      points="0,10 6,10 8,3 10,12 12,7 14,11 16,2 18,9 20,10 28,10 30,4 32,13 34,6 36,10 44,10 46,8 48,2 50,12 52,5 54,10 62,10 64,3 66,11 68,7 70,10 78,10 80,6 82,12 84,4 86,9 88,10 96,10 98,5 100,13 102,7 104,10 112,10 114,8 116,3 118,11 120,10"/>
    <line x1="0" y1="0" x2="0" y2="14" stroke="#5eead4" stroke-width="1" opacity=".85">
      <animate attributeName="x1" values="0;120;0" dur="2.8s" repeatCount="indefinite"/>
      <animate attributeName="x2" values="0;120;0" dur="2.8s" repeatCount="indefinite"/>
    </line>
  </svg>`;

  document.write(`<aside class="nav" id="site-nav">
    <div class="brand">
      <div class="brand-row">
        <img class="bn-logo" src="./assets/logo.png" alt="" width="40" height="40" />
        <div class="wm" aria-label="AI Radar">
          <span class="wm-ai">AI</span>
          <span class="wm-radar">RADAR</span>
          ${spec}
        </div>
      </div>
    </div>
    <div class="nav-sec">阅读</div>
    ${item("./index.html", "today", "今日必看", "bolt")}
    ${item("./practice.html", "practice", "博主实操", "list")}
    ${item("./week.html", "week", "本周归档", "file")}
    ${item("./tools-radar.html", "tools", "可试用工具", "grid")}
    <div class="nav-sec">订阅</div>
    ${item("./subscribe.html", "subscribe", "订阅更新", "rss")}
    ${item(FEISHU_GROUP, "feishu", "飞书订阅群", "rss", true)}
    ${item("./agent.html", "agent", "给 Agent 用", "agent")}
    <div class="nav-sec">说明</div>
    ${item("./about.html", "about", "这是什么", "info")}
  </aside>
  <div class="nav-backdrop" id="nav-backdrop"></div>`);

  function nav() { return document.getElementById("site-nav"); }
  function closeNav() {
    const el = nav();
    if (el) el.classList.remove("open");
    const backdrop = document.getElementById("nav-backdrop");
    if (backdrop) backdrop.classList.remove("show");
  }
  function openNav() {
    const el = nav();
    if (el) el.classList.add("open");
    const backdrop = document.getElementById("nav-backdrop");
    if (backdrop) backdrop.classList.add("show");
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-nav-open]")) {
      event.preventDefault();
      openNav();
      return;
    }
    if (event.target.id === "nav-backdrop") closeNav();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNav();
  });
  window.RadarShell = { open: openNav, close: closeNav };
})();
