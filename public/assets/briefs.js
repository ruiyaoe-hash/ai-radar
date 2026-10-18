/* 快讯层（L2）渲染。数据来自 ./briefs.json，失败时保留一句人话。 */
(function () {
  "use strict";

  var state = { lens: "all", items: [] };

  function make(tag, cls, value) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value !== undefined && value !== null) el.textContent = String(value);
    return el;
  }

  function safeLink(url, label) {
    var a = document.createElement("a");
    a.textContent = label;
    var href = typeof window.safeHref === "function" ? window.safeHref(url) : "";
    if (href) {
      a.href = href;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    }
    return a;
  }

  function renderItem(item) {
    var li = document.createElement("li");
    li.className = "brief";

    var meta = document.createElement("div");
    meta.className = "brief-meta";
    if (item.lens) meta.appendChild(make("span", "lens", item.lens));
    if (item.date) meta.appendChild(make("time", "", item.date));
    if (item.source) meta.appendChild(make("span", "origin", item.source));
    li.appendChild(meta);

    var title = document.createElement("h3");
    title.appendChild(safeLink(item.url, item.title || "未命名信号"));
    li.appendChild(title);

    if (item.summary) li.appendChild(make("p", "", item.summary));
    return li;
  }

  function render() {
    var host = document.getElementById("briefs");
    if (!host) return;
    var items = state.items.filter(function (item) {
      return state.lens === "all" || item.lens === state.lens;
    });
    host.textContent = "";

    if (!items.length) {
      host.appendChild(make("p", "empty", "这一栏暂时没有快讯。"));
      return;
    }

    host.appendChild(make("p", "brief-count", items.length + " 条"));
    var list = document.createElement("ul");
    list.className = "brief-list";
    items.forEach(function (item) {
      list.appendChild(renderItem(item));
    });
    host.appendChild(list);
  }

  function load() {
    fetch("./briefs.json?" + Date.now())
      .then(function (res) {
        if (!res.ok) throw new Error("briefs.json " + res.status);
        return res.json();
      })
      .then(function (data) {
        state.items = (data.items || []).slice().sort(function (a, b) {
          return String(b.date || "").localeCompare(String(a.date || ""));
        });
        var stamp = document.getElementById("updated");
        if (stamp && data.updated) stamp.textContent = "最近更新 " + data.updated;
        render();
      })
      .catch(function () {
        var host = document.getElementById("briefs");
        if (host) host.innerHTML = '<p class="empty">快讯还没准备好，稍后再来。</p>';
      });
  }

  var filters = document.getElementById("lensFilters");
  if (filters) {
    filters.addEventListener("click", function (event) {
      var button = event.target.closest("[data-lens]");
      if (!button) return;
      Array.prototype.forEach.call(filters.querySelectorAll(".chip"), function (el) {
        el.classList.remove("on");
      });
      button.classList.add("on");
      state.lens = button.dataset.lens;
      render();
    });
  }

  load();
})();
