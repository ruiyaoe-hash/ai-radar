/* 实战图谱：主题地图、主题手册、博主库。数据来自 data/kb.json。 */
(function () {
  const root = document.documentElement.getAttribute("data-root") || "./";
  const page = document.documentElement.getAttribute("data-page") || "";
  const slug = document.documentElement.getAttribute("data-slug") || "";
  const TYPE_ORDER = ["教程", "实战项目", "工具/开源", "方法论", "资源合集"];

  function asset(path) {
    return root + String(path || "").replace(/^\.\//, "");
  }

  function local(path) {
    return esc(hrefOf(asset(path)));
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function hrefOf(url) {
    return typeof window.safeHref === "function" ? window.safeHref(url) : "";
  }

  function extLink(url, labelHtml) {
    const href = hrefOf(url);
    if (!href) return "";
    return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${labelHtml}</a>`;
  }

  function formatNumber(n) {
    const v = Number(n) || 0;
    if (Math.abs(v) >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return v.toLocaleString("zh-CN");
  }

  function topicBySlug(kb) {
    const map = {};
    (kb.topics || []).forEach((topic) => { map[topic.slug] = topic; });
    return map;
  }

  function creatorByHandle(kb) {
    const map = {};
    (kb.creators || []).forEach((creator) => { map[creator.handle] = creator; });
    return map;
  }

  function sourcesFor(kb, topicSlug) {
    return (kb.sources || []).filter((source) => source.topic === topicSlug);
  }

  function demandTag(topic) {
    if (topic.status === "待采集" || typeof topic.save_ratio !== "number") return "";
    const when = topic.demand_refreshed_at ? "最近滚动 " + topic.demand_refreshed_at + "。" : "";
    const title = "平滑收藏比，样本少时向先验收缩。" + when + "不是原始收藏÷点赞，也不升降关注名单。";
    return `<span class="tag demand" title="${esc(title)}">需求信号 ${esc(Number(topic.save_ratio).toFixed(2))}</span>`;
  }

  function topicCard(topic) {
    const pending = topic.status === "待采集"
      ? `<span class="tag pending">待采集</span>`
      : "";
    return `<a class="topic-card" href="${local("topics/" + topic.slug + ".html")}">
      <div class="meta">${pending}<span>收录 ${esc(topic.source_count || 0)}</span><span>博主 ${esc(topic.creator_count || 0)}</span>${demandTag(topic)}</div>
      <h3>${esc(topic.name || "")}</h3>
      <p class="mean">${esc(topic.summary || "")}</p>
    </a>`;
  }

  function sourceCard(source, topic, showTopic) {
    const bits = [`<span class="tag prac">${esc(source.type || "实操")}</span>`];
    if (source.date) bits.push(`<span>${esc(source.date)}</span>`);
    if (source.origin === "practice" && source.verified === false) bits.push(`<span class="tag pending">未实机验证</span>`);
    if (typeof source.bookmarks === "number") bits.push(`<span>收藏 ${esc(formatNumber(source.bookmarks))}</span>`);
    if (typeof source.likes === "number") bits.push(`<span>点赞 ${esc(formatNumber(source.likes))}</span>`);
    const open = extLink(source.url, "打开原文");
    const topicLine = showTopic && topic
      ? `<p class="mean"><a href="${local("topics/" + topic.slug + ".html")}">${esc(topic.name)}</a></p>`
      : "";
    return `<article class="card" id="src-${esc(source.id)}">
      <div class="meta">${bits.join("")}</div>
      <h3>${esc(source.title || "")}</h3>
      ${source.excerpt ? `<p class="mean">${esc(source.excerpt)}</p>` : ""}
      <p class="fine">@${esc(source.author || "")}${open ? " · " + open : ""}</p>
      ${topicLine}
    </article>`;
  }

  function hayTopic(topic) {
    return [topic.name, topic.summary, topic.audience, ...(topic.tools || [])].join("\n").toLowerCase();
  }

  function hayCreator(creator) {
    return [creator.name, creator.handle, creator.focus].join("\n").toLowerCase();
  }

  function renderStats(kb) {
    const host = document.getElementById("atlas-stats");
    if (!host) return;
    const creators = (kb.creators || []).filter((creator) => (creator.source_count || 0) > 0).length;
    const rows = [
      [(kb.sources || []).length, "条实操分享"],
      [(kb.topics || []).length, "个主题"],
      [creators, "位博主"]
    ];
    host.innerHTML = rows.map(([n, label]) => `<div><strong>${esc(n)}</strong><span>${label}</span></div>`).join("");
  }

  function renderTracks(kb, query) {
    const q = (query || "").trim().toLowerCase();
    const matchedCreators = q
      ? (kb.creators || []).filter((creator) => (creator.source_count || 0) > 0 && hayCreator(creator).includes(q))
      : [];
    const fromCreators = new Set();
    matchedCreators.forEach((creator) => (creator.topics || []).forEach((id) => fromCreators.add(id)));
    let shown = 0;
    (kb.tracks || []).forEach((track) => {
      const host = document.querySelector(`[data-track="${track.id}"]`);
      const block = host ? host.closest(".track-block") : null;
      if (!host) return;
      const list = (kb.topics || []).filter((topic) => topic.track === track.id).filter((topic) => {
        if (!q) return true;
        return hayTopic(topic).includes(q) || fromCreators.has(topic.slug);
      });
      shown += list.length;
      host.innerHTML = list.length
        ? list.map(topicCard).join("")
        : (q ? "" : `<p class="empty">这个方向下面还没有主题。</p>`);
      if (block) block.hidden = Boolean(q && !list.length);
    });
    const results = document.getElementById("atlas-results");
    if (!results) return;
    if (!q) {
      results.hidden = true;
      results.innerHTML = "";
      return;
    }
    const topics = topicBySlug(kb);
    const people = matchedCreators.map((creator) => {
      const links = (creator.topics || []).map((id) => {
        const topic = topics[id];
        if (!topic) return "";
        return `<a href="${local("topics/" + topic.slug + ".html")}">${esc(topic.name)}</a>`;
      }).filter(Boolean).join(" · ");
      return `<p class="mean"><a href="${local("creators.html#creator-" + creator.handle)}">${esc(creator.name)}</a> <span class="fine">@${esc(creator.handle)}</span>${links ? " · " + links : ""}</p>`;
    }).join("");
    results.hidden = false;
    if (!shown && !matchedCreators.length) {
      results.innerHTML = `<p class="empty">没有对上的主题或博主。换一个工具名、主题名或博主名再试。</p>`;
      return;
    }
    results.innerHTML = people
      ? `<h2>对上的博主</h2>${people}`
      : `<p class="fine">上面是对上的主题。</p>`;
  }

  function bindSearch(kb) {
    const input = document.getElementById("atlas-search");
    const suggest = document.getElementById("atlas-suggest");
    if (!input) return;
    const suggestions = ["ESP32", "PCB", "分镜", "Skill", "播客", "Seedance", "Magpie"];
    if (suggest && !suggest.childElementCount) {
      suggest.innerHTML = suggestions.map((word) => `<button class="chip" type="button" data-q="${esc(word)}">${esc(word)}</button>`).join("");
      suggest.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-q]");
        if (!btn) return;
        input.value = btn.getAttribute("data-q") || "";
        renderTracks(kb, input.value);
        input.focus();
      });
    }
    input.addEventListener("input", () => renderTracks(kb, input.value));
  }

  function loadToday() {
    const host = document.getElementById("today-compact");
    if (!host) return;
    fetch(asset("today3.txt?") + Date.now()).then((res) => {
      if (!res.ok) throw new Error("today");
      return res.text();
    }).then((text) => {
      const lines = text.split("\n").map((line) => line.trim()).filter((line) => /^\d+\.\s/.test(line)).slice(0, 3);
      host.innerHTML = lines.length
        ? lines.map((line) => `<li>${esc(line.replace(/^\d+\.\s*/, ""))}</li>`).join("")
        : "<li>今日精选还在准备，稍后再来。</li>";
    }).catch(() => {
      host.innerHTML = "<li>今日精选还在准备，稍后再来。</li>";
    });
  }

  function renderHome(kb) {
    renderStats(kb);
    renderTracks(kb, "");
    const note = document.getElementById("snapshot-note");
    if (note) {
      const when = kb.demand_refreshed_at || kb.updated || "";
      note.textContent = "需求信号滚动于 " + when + "。这是平滑后的收藏比，样本少时向先验收缩；没有更新的互动数时沿用图谱源里的计数。关注名单不按这个数自动升降。";
    }
    const latestHost = document.getElementById("latest-list");
    if (latestHost) {
      const topics = topicBySlug(kb);
      const latest = (kb.sources || []).slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 6);
      latestHost.innerHTML = latest.map((source) => sourceCard(source, topics[source.topic], true)).join("");
    }
    bindSearch(kb);
    loadToday();
  }

  function topicHeader(topic, track) {
    const tools = (topic.tools || []).map((tool) => `<span class="tag">${esc(tool)}</span>`).join("");
    const stats = [];
    if ((topic.source_count || 0) > 0) {
      stats.push(`<span><b>${esc(topic.source_count)}</b> 条实操</span>`);
      stats.push(`<span><b>${esc(topic.creator_count || 0)}</b> 位博主贡献</span>`);
      if (topic.has_bookmarks) stats.push(`<span>累计收藏 <b>${esc(formatNumber(topic.bookmarks || 0))}</b></span>`);
      if (typeof topic.save_ratio === "number") {
        const samples = topic.demand_samples ? " · " + topic.demand_samples + " 条样本" : "";
        stats.push(`<span>需求信号 <b>${esc(Number(topic.save_ratio).toFixed(2))}</b>${esc(samples)}</span>`);
      }
      if (topic.demand_refreshed_at) stats.push(`<span>滚动于 ${esc(topic.demand_refreshed_at)}</span>`);
      if (topic.latest) stats.push(`<span>最近更新 ${esc(topic.latest)}</span>`);
    }
    return `<p class="back"><a href="${local("atlas.html")}">全部主题</a></p>
      <header class="topic-head">
        <p class="eyebrow">${esc(track ? track.name : "")}</p>
        <h1>${esc(topic.name || "")}</h1>
        <p class="sub">${esc(topic.summary || "")}</p>
        <p class="mean"><b>适合：</b>${esc(topic.audience || "")}</p>
        <div class="meta">${tools}</div>
        ${stats.length ? `<div class="stat-line">${stats.join("")}</div>` : ""}
      </header>`;
  }

  function collecting() {
    return `<div class="collecting">
      <h2>这个主题还在采集中</h2>
      <p>收录标准是编号步骤、物料清单（BOM）、安装命令，或一个可打开的仓库。凑够能照着做的分享之后，这里会生成手册。</p>
    </div>`;
  }

  function renderTopic(kb) {
    const host = document.getElementById("topic-root");
    if (!host) return;
    const topic = (kb.topics || []).find((item) => item.slug === slug);
    if (!topic) {
      host.innerHTML = `<p class="empty">这个地址还没有对应的主题。回到<a href="${local("atlas.html")}">实战图谱</a>看看现有主题。</p>`;
      return;
    }
    const track = (kb.tracks || []).find((item) => item.id === topic.track);
    const items = sourcesFor(kb, slug);
    if (!items.length || topic.status === "待采集") {
      host.innerHTML = topicHeader(topic, track) + collecting();
      return;
    }
    const indexOf = {};
    items.forEach((source, index) => { indexOf[source.id] = index + 1; });
    const steps = (topic.playbook || []).map((step, index) => {
      const cites = (step.sources || []).map((id) => {
        const n = indexOf[id];
        const source = items.find((item) => item.id === id);
        if (!n || !source) return "";
        return `<a class="cite" href="#src-${esc(id)}">[${n}·@${esc(source.author)}]</a>`;
      }).join("");
      return `<li class="step"><span class="step-no">${index + 1}</span><div><h3>${esc(step.title || "")}</h3><p class="mean">${esc(step.detail || "")}${cites}</p></div></li>`;
    }).join("");
    const pitfalls = (topic.pitfalls || []).length
      ? `<div class="pitfalls"><h3>踩过的坑</h3><ul>${topic.pitfalls.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
      : "";
    const authors = [];
    items.forEach((source) => {
      if (authors.indexOf(source.author) < 0) authors.push(source.author);
    });
    const creators = creatorByHandle(kb);
    const side = authors.map((handle) => {
      const creator = creators[handle] || { name: handle, focus: "", profile_url: "https://x.com/" + handle };
      const n = items.filter((source) => source.author === handle).length;
      const link = extLink(creator.profile_url, `<span class="who">${esc(creator.name || handle)}</span><span class="fine">${esc(creator.focus || "")}</span>`);
      return `<div class="side-card">${link || esc(creator.name || handle)}<span class="count">${n} 条</span></div>`;
    }).join("");
    host.innerHTML = `${topicHeader(topic, track)}
      <div class="topic-layout">
        <div>
          <section>
            <h2>实操手册</h2>
            <p class="sub">由多位博主的分享合并而成。角标跳到下面的原帖，编号对应该主题素材的原始顺序。</p>
            ${(topic.unverified_practice || 0) > 0 ? `<p class="sub">这里有 ${esc(topic.unverified_practice)} 条尚未实机验证的实操，手册还不是完备课程。</p>` : ""}
            <ol class="steps">${steps}</ol>
            ${pitfalls}
          </section>
          <section>
            <h2>原帖素材 · ${esc(items.length)}</h2>
            <div class="filters" id="type-filters"></div>
            <div class="filters" id="sort-filters">
              <button class="chip on" type="button" data-sort="bookmarks">按收藏</button>
              <button class="chip" type="button" data-sort="date">按时间</button>
            </div>
            <div id="source-list"></div>
          </section>
        </div>
        <aside>
          <h2 class="side-title">贡献博主</h2>
          ${side}
        </aside>
      </div>`;
    bindSourceList(items, indexOf);
  }

  function bindSourceList(items, indexOf) {
    const typeHost = document.getElementById("type-filters");
    const listHost = document.getElementById("source-list");
    const present = TYPE_ORDER.filter((type) => items.some((source) => source.type === type));
    items.forEach((source) => {
      if (source.type && present.indexOf(source.type) < 0) present.push(source.type);
    });
    const state = { type: "all", sort: "bookmarks" };
    if (typeHost) {
      typeHost.innerHTML = [`<button class="chip on" type="button" data-type="all">全部</button>`]
        .concat(present.map((type) => `<button class="chip" type="button" data-type="${esc(type)}">${esc(type)}</button>`))
        .join("");
      typeHost.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-type]");
        if (!btn) return;
        typeHost.querySelectorAll(".chip").forEach((el) => el.classList.remove("on"));
        btn.classList.add("on");
        state.type = btn.getAttribute("data-type") || "all";
        draw();
      });
    }
    const sortHost = document.getElementById("sort-filters");
    if (sortHost) {
      sortHost.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-sort]");
        if (!btn) return;
        sortHost.querySelectorAll(".chip").forEach((el) => el.classList.remove("on"));
        btn.classList.add("on");
        state.sort = btn.getAttribute("data-sort") || "bookmarks";
        draw();
      });
    }
    function draw() {
      const rows = items.filter((source) => state.type === "all" || source.type === state.type).slice();
      rows.sort((a, b) => {
        if (state.sort === "date") return String(b.date || "").localeCompare(String(a.date || ""));
        const left = typeof a.bookmarks === "number" ? a.bookmarks : -1;
        const right = typeof b.bookmarks === "number" ? b.bookmarks : -1;
        if (right !== left) return right - left;
        return String(b.date || "").localeCompare(String(a.date || ""));
      });
      if (!listHost) return;
      if (!rows.length) {
        listHost.innerHTML = `<p class="empty">这一类下面还没有原帖。</p>`;
        return;
      }
      listHost.innerHTML = rows.map((source) => {
        const card = sourceCard(source, null, false);
        const n = indexOf[source.id];
        return card.replace(`<div class="meta">`, `<div class="meta"><span class="tag">素材 ${esc(n)}</span>`);
      }).join("");
    }
    draw();
  }

  function renderCreators(kb) {
    const host = document.getElementById("creator-list");
    if (!host) return;
    const topics = topicBySlug(kb);
    const rows = (kb.creators || []).filter((creator) => (creator.source_count || 0) > 0);
    if (!rows.length) {
      host.innerHTML = `<p class="empty">还没有收录博主。</p>`;
      return;
    }
    host.className = "creator-grid";
    host.innerHTML = rows.map((creator) => {
      const metric = creator.bookmark_metric
        ? `<strong>${esc(formatNumber(creator.bookmarks || 0))}</strong><span>被收藏</span>`
        : `<strong>${esc(creator.source_count || 0)}</strong><span>收录</span>`;
      const fans = typeof creator.followers === "number"
        ? ` · ${esc(formatNumber(creator.followers))} 粉丝`
        : "";
      const name = extLink(creator.profile_url, esc(creator.name || creator.handle));
      const chips = (creator.topics || []).map((id) => {
        const topic = topics[id];
        if (!topic) return "";
        return `<a class="tag" href="${local("topics/" + topic.slug + ".html")}">${esc(topic.name)}</a>`;
      }).join("");
      return `<article class="card" id="creator-${esc(creator.handle)}">
        <div class="creator-top">
          <div>
            <h3>${name || esc(creator.name || creator.handle)}</h3>
            <p class="fine">@${esc(creator.handle)}${fans}</p>
          </div>
          <div class="metric">${metric}</div>
        </div>
        <p class="mean">${esc(creator.focus || "")}</p>
        <div class="meta">${chips}</div>
      </article>`;
    }).join("");
  }

  function fail(message) {
    const host = document.getElementById("topic-root")
      || document.getElementById("creator-list")
      || document.getElementById("latest-list");
    if (host) host.innerHTML = `<p class="empty">${esc(message)}</p>`;
  }

  fetch(asset("data/kb.json?") + Date.now()).then((res) => {
    if (!res.ok) throw new Error("kb");
    return res.json();
  }).then((kb) => {
    if (slug) renderTopic(kb);
    else if (page === "creators") renderCreators(kb);
    else renderHome(kb);
  }).catch(() => {
    fail("暂时读不到主题数据。");
  });
})();
