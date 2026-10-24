/* 专题观察：长期看法和随笔。不展示原始分数，也不展示机器 id。 */
(function () {
  "use strict";

  function esc(text) {
    return String(text || "").replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function fill(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  var STATUS = { "待定": "还在观察", "命中": "已经对上", "未命中": "没有对上" };

  function renderWatch(item) {
    var href = typeof window.safeHref === "function" ? window.safeHref(item.url || "") : "";
    var link = href ? `<p><a href="${esc(href)}" target="_blank" rel="noopener">打开原文</a></p>` : "";
    var source = item.source ? `<p class="src"><span>${esc(item.source)}</span></p>` : "";
    var fold = source + link;
    var details = fold.trim()
      ? `<details><summary>背景与出处</summary><div class="fold">${fold}</div></details>`
      : "";
    return `<article class="card">
      <div class="meta"><span>${esc(item.date || "")}</span></div>
      <h3>${esc(item.title || "")}</h3>
      <p class="mean"><b>发生了什么：</b>${esc(item.summary || "")}</p>
      <p class="mean"><b>为什么值得看：</b>${esc(item.why || "")}</p>
      <p class="mean"><b>对我有什么影响：</b>${esc(item.affect || "")}</p>
      ${details}
    </article>`;
  }

  function loadWatch() {
    fetch("./data/watch.json?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error("watch");
      return res.json();
    }).then(function (data) {
      var items = (Array.isArray(data.items) ? data.items : []).filter(function (item) {
        return item && item.title && item.summary && item.why && item.affect;
      });
      if (!items.length) {
        fill("watch", '<p class="empty">跨过一天仍然值得跟踪的领域进展，写清楚之后会出现在这里。</p>');
        return;
      }
      fill("watch", items.map(renderWatch).join(""));
    }).catch(function () {
      fill("watch", '<p class="empty">领域进展暂时读不到。长期看法和随笔仍然可以看。</p>');
    });
  }

  function load() {
    loadWatch();
    fetch("./theses.json?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error("theses");
      return res.json();
    }).then(function (data) {
      var theses = Array.isArray(data.theses) ? data.theses : [];
      if (!theses.length) {
        fill("theses", '<p class="empty">写成完整看法之后，会出现在这里。</p>');
        return;
      }
      fill("theses", theses.map(function (item) {
        var status = STATUS[item.status] || "还在观察";
        var horizon = item.horizon ? `<span>${esc(item.horizon)}</span>` : "";
        var kill = item.falsifier
          ? `<p class="mean"><b>什么情况下这条看法不再成立：</b>${esc(item.falsifier)}</p>`
          : "";
        return `<article class="card">
          <div class="meta"><span class="tag">${esc(status)}</span>${horizon}</div>
          <h3>${esc(item.statement || "")}</h3>
          ${kill}
        </article>`;
      }).join(""));
    }).catch(function () {
      fill("theses", '<p class="empty">长期看法暂时读不到。随笔仍然可以打开。</p>');
    });

    fetch("./blog/posts.json?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error("posts");
      return res.json();
    }).then(function (data) {
      var posts = Array.isArray(data.posts) ? data.posts : [];
      if (!posts.length) {
        fill("posts", '<p class="empty">还没有随笔。第一篇写好后会出现在这里。</p>');
        return;
      }
      fill("posts", posts.map(function (post) {
        var href = typeof window.safeHref === "function"
          ? window.safeHref("./blog/" + encodeURIComponent(post.slug || "") + ".html")
          : "";
        var title = href
          ? `<a href="${esc(href)}">${esc(post.title || "")}</a>`
          : esc(post.title || "");
        return `<article class="card">
          <div class="meta"><span>${esc(post.date || "")}</span><span>约 ${esc(String(post.minutes || 1))} 分钟</span></div>
          <h3>${title}</h3>
          ${post.summary ? `<p class="mean">${esc(post.summary)}</p>` : ""}
        </article>`;
      }).join(""));
    }).catch(function () {
      fill("posts", '<p class="empty">随笔暂时读不到，可以直接打开<a href="./blog/">随笔</a>。</p>');
    });
  }

  load();
})();
