(function () {
  const R = window.Radar;
  const esc = R.esc;
  const safeHref = window.safeHref;
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function typewriter() {
    const el = document.getElementById("typing");
    if (!el || reduceMotion) return;
    const text = el.textContent;
    const chars = Array.from(text);
    el.textContent = "";
    let i = 0;
    function step() {
      i += 1;
      el.textContent = chars.slice(0, i).join("");
      if (i < chars.length) setTimeout(step, chars[i - 1] === "，" ? 320 : 110);
    }
    setTimeout(step, 900);
  }

  function accordion() {
    document.querySelectorAll(".accordion-header").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = document.getElementById(btn.getAttribute("aria-controls"));
        const open = btn.getAttribute("aria-expanded") !== "true";
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (panel) panel.hidden = !open;
      });
    });
  }

  function liveNote() {
    document.addEventListener("radar:live", (event) => {
      const detail = event.detail || {};
      const dot = document.getElementById("home-live");
      const text = document.getElementById("live-text");
      if (dot) dot.classList.add(detail.live ? "live" : "idle");
      if (text && detail.at) {
        text.textContent = detail.live
          ? `信号灯亮着：最近更新 ${detail.at}（北京时间）`
          : `上次更新 ${detail.at}（北京时间）。北京时间每天 08:00 主报，工作日 21:00 晚班`;
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

  function stat(value, label) {
    return `<div><strong>${esc(String(value))}</strong><span>${esc(label)}</span></div>`;
  }
  function fill(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }
  function fail(id, text, href, label) {
    fill(id, `<li class="empty">${esc(text)}<a href="${esc(href)}">${esc(label)}</a>。</li>`);
  }
  function featured(href, meta, title, body, external) {
    const safe = safeHref(href);
    const blank = external ? ' target="_blank" rel="noopener noreferrer"' : "";
    const inner = `<div class="meta">${meta}</div><h4>${esc(title)}</h4>${body ? `<p>${esc(body)}</p>` : ""}`;
    return safe
      ? `<li><a class="featured-item" href="${esc(safe)}"${blank}>${inner}</a></li>`
      : `<li><div class="featured-item">${inner}</div></li>`;
  }

  function loadSignals() {
    Promise.all([getJSON("./items.json"), getText("./today3.txt").catch(() => "")])
      .then(([items, today3]) => {
        const list = Array.isArray(items.items) ? items.items : [];
        const model = R.heroModel(today3, list);
        const rows = model.rows.slice(0, 3);
        fill("home-today", rows.length
          ? rows.map((row) => featured("./today.html", '<span class="tag must">今日精选</span>', row.title, row.mean || row.suggest, false)).join("")
          : '<li class="empty">今日精选还在准备，稍后再来；也可以先看<a href="./week.html">本周归档</a>。</li>');
        const must = list.filter((it) => R.bandOf(it) === "must").length;
        fill("signal-stats", stat(list.length, "近 7 天信号") + stat(must, "其中必看"));
        return getJSON("./briefs.json").then((briefs) => {
          const rowsB = (Array.isArray(briefs.items) ? briefs.items : []).slice(0, 3);
          const stats = document.getElementById("signal-stats");
          if (stats) stats.insertAdjacentHTML("beforeend", stat((briefs.items || []).length, "在架快讯"));
          fill("home-briefs", rowsB.length
            ? rowsB.map((b) => featured(b.url,
              `<span>${esc(b.date || "")}</span><span>${esc(b.source || "")}</span>${b.lens ? `<span class="tag">${esc(R.LENS_LABEL[b.lens] || b.lens)}</span>` : ""}`,
              b.title, b.summary, true)).join("")
            : '<li class="empty">这几天还没有快讯。</li>');
        }).catch(() => fail("home-briefs", "快讯暂时读不到，可以直接打开", "./briefs.html", "快讯页"));
      })
      .catch(() => {
        fail("home-today", "信号暂时读不到，可以直接打开", "./today.html", "今日必看");
        fail("home-briefs", "快讯暂时读不到，可以直接打开", "./briefs.html", "快讯页");
      });
  }

  function loadAtlas() {
    getJSON("./data/kb.json").then((kb) => {
      const topics = Array.isArray(kb.topics) ? kb.topics : [];
      const active = topics.filter((t) => t.status !== "待采集");
      fill("atlas-mini",
        stat(active.length, "主题手册") +
        stat(Array.isArray(kb.sources) ? kb.sources.length : 0, "条原帖做法") +
        stat(Array.isArray(kb.creators) ? kb.creators.length : 0, "位实操博主"));
      const top = active
        .slice()
        .sort((a, b) => (Number(b.bookmarks) || 0) - (Number(a.bookmarks) || 0))
        .slice(0, 3);
      fill("home-topics", top.length
        ? top.map((t) => featured(`./topics/${encodeURIComponent(t.slug)}.html`,
          `<span>${esc(String(t.source_count || 0))} 条做法</span><span>${esc(String(t.creator_count || 0))} 位博主</span>${t.latest ? `<span>更新 ${esc(t.latest)}</span>` : ""}`,
          t.name, t.summary, false)).join("")
        : '<li class="empty">主题还在采集，先看看<a href="./practice.html">博主实操</a>。</li>');
    }).catch(() => fail("home-topics", "图谱暂时读不到，可以直接打开", "./atlas.html", "实战图谱"));
  }

  function loadPosts() {
    getJSON("./blog/posts.json").then((doc) => {
      const posts = (Array.isArray(doc.posts) ? doc.posts : []).slice(0, 3);
      fill("home-posts", posts.length
        ? posts.map((p) => featured(`./blog/${encodeURIComponent(p.slug)}.html`,
          `<span>${esc(p.date || "")}</span><span>约 ${esc(String(p.minutes || 1))} 分钟</span>`,
          p.title, p.summary, false)).join("")
        : '<li class="empty">还没有随笔。第一篇写好后会出现在这里。</li>');
    }).catch(() => fail("home-posts", "随笔暂时读不到，可以直接打开", "./blog/", "随笔页"));
  }

  liveNote();
  accordion();
  typewriter();
  loadSignals();
  loadAtlas();
  loadPosts();
})();
