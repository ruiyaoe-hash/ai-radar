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
  function getText(path) {
    return fetch(path + "?" + Date.now()).then((res) => {
      if (!res.ok) throw new Error(path);
      return res.text();
    });
  }

  function fill(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }
  function fail(id, text, href, label) {
    fill(id, `<p class="empty">${esc(text)}<a href="${esc(href)}">${esc(label)}</a>。</p>`);
  }

  function loadPicks() {
    Promise.all([getJSON("./items.json"), getText("./today3.txt").catch(() => "")])
      .then(([items, today3]) => {
        const list = Array.isArray(items.items) ? items.items : [];
        const model = R.heroModel(today3, list);
        const rows = model.rows.slice(0, 3);
        const byTitle = new Map(list.filter((it) => it.title).map((it) => [String(it.title).trim(), it]));
        fill("home-today", rows.length
          ? rows.map((row) => {
            const it = byTitle.get(String(row.title || "").trim());
            return it ? R.renderCard(it, model.featured, { compact: true }) : R.renderHero([row]);
          }).join("")
          : '<p class="empty">今日精选还在准备，稍后再来。也可以先看<a href="./briefs.html">最新动态</a>。</p>');
        loadChanges(list, model.featured);
      })
      .catch(() => {
        fail("home-today", "今日精选暂时读不到，可以直接打开", "./today.html", "今日重点");
        fail("home-changes", "最近的变化暂时读不到，可以直接打开", "./briefs.html", "最新动态");
      });
  }

  function loadChanges(list, featured) {
    const rest = (list || []).filter((it) => !(it.id && featured && featured.has(it.id)));
    const slice = rest.slice(0, 4);
    fill("home-changes", slice.length
      ? slice.map((it) => R.renderCard(it, featured, { compact: true })).join("")
      : '<p class="empty">精选之外这几天还没有更多变化。完整时间流在<a href="./briefs.html">最新动态</a>。</p>');
  }

  function loadTools() {
    const rings = [
      ["采纳", "值得采用"],
      ["试用", "可以试用"],
      ["评估", "需要评估"],
      ["暂缓", "暂缓跟进"]
    ];
    getJSON("./tools-radar.json").then((data) => {
      const groups = data.rings || {};
      fill("home-tools", rings.map(([key, title]) => {
        const list = (groups[key] || []).slice(0, 2);
        const body = list.length
          ? list.map((it) => {
            const href = R.safeHref(it.try_url || it.url || "");
            const titleHtml = href
              ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(it.title || "")}</a>`
              : esc(it.title || "");
            const step = it.first_step ? `<p class="mean">${esc(it.first_step)}</p>` : "";
            return `<div class="tool-item"><div>${titleHtml}</div>${step}</div>`;
          }).join("")
          : '<p class="empty">这一档还没有。</p>';
        return `<section class="card ring"><h3>${esc(title)}</h3>${body}</section>`;
      }).join(""));
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
      fill("home-methods", html || '<p class="empty">手册还在整理。可以先打开<a href="./atlas.html">实战手册</a>看看现有主题。</p>');
    }).catch(() => fail("home-methods", "手册暂时读不到，可以直接打开", "./atlas.html", "实战手册"));
  }

  liveNote();
  loadPicks();
  loadTools();
  loadMethods();
})();
