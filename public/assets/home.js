(function () {
  const R = window.Radar;
  const esc = R.esc;

  function liveNote() {
    document.addEventListener("radar:live", (event) => {
      const detail = event.detail || {};
      const dot = document.getElementById("home-live");
      const text = document.getElementById("live-text");
      if (dot) dot.classList.add(detail.live ? "live" : "idle");
      if (text && detail.at) {
        text.textContent = `最近更新 ${detail.at}（北京时间）。每条判断都链回原文。`;
      }
    });
  }

  function getJSON(path) {
    return fetch(path + "?" + Date.now()).then((res) => {
      if (!res.ok) throw new Error(path);
      return res.json();
    });
  }
  function fill(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }
  function fail(id, text, href, label) {
    fill(id, `<p class="empty">${esc(text)}<a href="${esc(href)}">${esc(label)}</a>。</p>`);
  }

  function normUrl(url) {
    return String(url || "").trim().replace(/\/+$/, "").toLowerCase();
  }

  function blockedFrom(picks) {
    const urls = new Set();
    const ids = new Set();
    (picks.blocked_urls || []).forEach((url) => { if (url) urls.add(normUrl(url)); });
    (picks.blocked_ids || []).forEach((id) => { if (id) ids.add(id); });
    (picks.days || []).forEach((day) => {
      (day.items || []).forEach((item) => {
        if (item.id) ids.add(item.id);
        if (item.candidate_id) ids.add(item.candidate_id);
        if (item.url) urls.add(normUrl(item.url));
        (item.sources || []).forEach((source) => {
          if (source && source.url) urls.add(normUrl(source.url));
        });
      });
    });
    return { urls, ids };
  }

  function loadPicks() {
    getJSON("./picks.json").then((data) => {
      const days = Array.isArray(data.days) ? data.days : [];
      const newest = days.find((day) => Array.isArray(day.items) && day.items.length);
      const items = newest ? newest.items : [];
      fill("home-today", items.length
        ? items.map((it) => R.renderCard(it, new Set())).join("")
        : '<p class="empty">最新一天还没有精选。可以先看<a href="./briefs.html">信息简讯</a>。</p>');
    }).catch(() => fail("home-today", "信息精选暂时读不到，可以直接打开", "./today.html", "信息精选"));
  }

  function loadBriefs() {
    Promise.all([
      getJSON("./briefs.json").catch(() => ({ items: [] })),
      getJSON("./picks.json").catch(() => ({ days: [], blocked_urls: [], blocked_ids: [] }))
    ]).then(([data, picks]) => {
      const block = blockedFrom(picks || {});
      const items = (Array.isArray(data.items) ? data.items : []).filter((item) => {
        if (item.id && block.ids.has(item.id)) return false;
        if (item.candidate_id && block.ids.has(item.candidate_id)) return false;
        if (item.url && block.urls.has(normUrl(item.url))) return false;
        return true;
      }).slice(0, 4);
      fill("home-changes", items.length
        ? items.map((it) => R.renderFactCard(it)).join("")
        : '<p class="empty">这几天还没有简讯。完整列表在<a href="./briefs.html">信息简讯</a>。</p>');
    }).catch(() => fail("home-changes", "信息简讯暂时读不到，可以直接打开", "./briefs.html", "信息简讯"));
  }

  function loadTools() {
    getJSON("./tools-radar.json").then((data) => {
      const items = (Array.isArray(data.stream) ? data.stream : [])
        .filter((it) => it.summary && it.audience_value && it.first_step)
        .slice(0, 4);
      fill("home-tools", items.length
        ? items.map((it) => {
          const href = R.safeHref(it.try_url || it.url || "");
          const title = href
            ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(it.title || "")}</a>`
            : esc(it.title || "");
          const stance = it.stance ? `<span class="tag">${esc(it.stance)}</span>` : "";
          return `<article class="card"><div class="meta">${stance}</div><h3>${title}</h3><p class="mean"><b>摘要：</b>${esc(it.summary)}</p><p class="mean"><b>大众价值：</b>${esc(it.audience_value)}</p><p class="mean"><b>上手实验：</b>${esc(it.first_step)}</p></article>`;
        }).join("")
        : '<p class="empty">最近还没有要决定的工具。可以打开<a href="./tools-radar.html">工具决策</a>。</p>');
    }).catch(() => fail("home-tools", "工具列表暂时读不到，可以直接打开", "./tools-radar.html", "工具决策"));
  }

  function loadMethods() {
    Promise.all([
      getJSON("./practice.json").catch(() => ({ items: [] })),
      getJSON("./data/kb.json").catch(() => ({ topics: [] }))
    ]).then(([practice, kb]) => {
      const items = (Array.isArray(practice.items) ? practice.items : []).slice(0, 2);
      const topics = (Array.isArray(kb.topics) ? kb.topics : [])
        .filter((topic) => topic.status !== "待采集")
        .slice()
        .sort((a, b) => (Number(b.bookmarks) || 0) - (Number(a.bookmarks) || 0))
        .slice(0, 2);
      const practiceHtml = items.map((it) => {
        const href = R.safeHref("./practice.html#" + encodeURIComponent(it.id || ""));
        const title = href
          ? `<a href="${esc(href)}">${esc(it.title || "")}</a>`
          : esc(it.title || "");
        return `<article class="card"><div class="meta"><span class="tag prac">${esc(it.kind || "做法")}</span></div><h3>${title}</h3>${it.takeaway ? `<p class="mean">${esc(it.takeaway)}</p>` : ""}</article>`;
      }).join("");
      const topicHtml = topics.map((topic) => {
        const href = R.safeHref("./topics/" + encodeURIComponent(topic.slug || "") + ".html");
        const title = href
          ? `<a href="${esc(href)}">${esc(topic.name || "")}</a>`
          : esc(topic.name || "");
        return `<article class="card"><div class="meta"><span class="tag">主题手册</span><span>${esc(String(topic.source_count || 0))} 条做法</span></div><h3>${title}</h3>${topic.summary ? `<p class="mean">${esc(topic.summary)}</p>` : ""}</article>`;
      }).join("");
      const html = practiceHtml + topicHtml;
      fill("home-methods", html || '<p class="empty">能照着做的步骤和主题手册会出现在这里。可以先打开<a href="./atlas.html">实战手册</a>。</p>');
    }).catch(() => fail("home-methods", "手册暂时读不到，可以直接打开", "./atlas.html", "实战手册"));
  }

  liveNote();
  loadPicks();
  loadBriefs();
  loadTools();
  loadMethods();
})();
