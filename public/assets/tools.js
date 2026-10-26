/* 工具决策：按时间往下排。每条写清摘要、大众价值、上手实验。 */
(function () {
  "use strict";

  var state = { groups: [], focus: "" };
  var genericHost = { "github.com": 1, "x.com": 1, "twitter.com": 1, "t.co": 1, "youtube.com": 1, "youtu.be": 1 };

  function loadJson(path) {
    return fetch(path + "?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error(path);
      return res.json();
    });
  }

  function hostOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
    } catch (err) {
      return "";
    }
  }

  function visibleGroups() {
    if (!state.focus) return state.groups;
    return state.groups.filter(function (group) { return group.date === state.focus; });
  }

  function related(tool, practices) {
    var raw = String(tool.try_url || tool.url || "").replace(/\/+$/, "");
    var exact = practices.find(function (item) { return String(item.url || "").replace(/\/+$/, "") === raw; });
    var host = hostOf(raw);
    var hit = exact || ((!host || genericHost[host]) ? null : practices.find(function (item) { return hostOf(item.url) === host; }));
    var bits = [];
    if (tool.id) {
      var release = Radar.safeHref("./briefs.html#day-" + encodeURIComponent(tool.date || ""));
      if (release) bits.push('<a href="' + Radar.esc(release) + '">相关发布</a>');
    }
    if (hit) {
      var href = Radar.safeHref("./practice.html#" + encodeURIComponent(hit.id || ""));
      if (href) bits.push('<a href="' + Radar.esc(href) + '">相关做法</a>');
    }
    return bits.length ? '<p class="mean">' + bits.join(" · ") + "</p>" : "";
  }

  function visitorStance(raw) {
    var text = String(raw || "");
    if (text === "推荐使用" || text === "采纳" || text === "试用" || text === "值得采用" || text === "可以试用") return "推荐使用";
    if (text === "值得关注" || text === "评估" || text === "暂缓" || text === "需要评估" || text === "暂缓跟进") return "值得关注";
    return text ? "值得关注" : "";
  }

  function renderTool(tool, practices) {
    var href = Radar.safeHref(tool.try_url || tool.url || "");
    var title = href
      ? '<a href="' + Radar.esc(href) + '" target="_blank" rel="noopener">' + Radar.esc(tool.title || "") + "</a>"
      : Radar.esc(tool.title || "");
    var stanceLabel = visitorStance(tool.stance);
    var stance = stanceLabel ? '<span class="tag">' + Radar.esc(stanceLabel) + "</span>" : "";
    return '<article class="card tool-stream" id="' + Radar.esc(tool.id || "") + '">' +
      '<div class="meta">' + stance + (tool.date ? "<span>" + Radar.esc(tool.date) + "</span>" : "") + "</div>" +
      "<h3>" + title + "</h3>" +
      '<p class="mean field"><b>摘要：</b>' + Radar.esc(tool.summary || "") + "</p>" +
      '<p class="mean field"><b>大众价值：</b>' + Radar.esc(tool.audience_value || "") + "</p>" +
      '<p class="mean field"><b>上手实验：</b>' + Radar.esc(tool.first_step || "") + "</p>" +
      related(tool, practices) +
      "</article>";
  }

  function load() {
    Promise.all([
      loadJson("./tools-radar.json"),
      loadJson("./practice.json").catch(function () { return { items: [] }; })
    ]).then(function (pair) {
      var data = pair[0];
      var practices = (pair[1] && pair[1].items) || [];
      var items = Array.isArray(data.stream) ? data.stream.slice() : [];
      if (!items.length) {
        ["推荐使用", "值得关注", "采纳", "试用", "评估", "暂缓"].forEach(function (key) {
          ((data.rings || {})[key] || []).forEach(function (item) { items.push(item); });
        });
      }
      items = items.filter(function (item) { return item.summary && item.audience_value && item.first_step; });
      state.groups = DayStream.groupByDate(items, function (item) { return item.date; });
      var stamp = document.getElementById("updated");
      if (stamp && data.updated) stamp.textContent = "最近更新 " + data.updated;
      DayStream.fillSelect(document.getElementById("dayJump"), state.groups.map(function (group) { return group.date; }));
      var host = document.getElementById("stream");
      function draw() {
        var groups = state.focus ? state.groups.filter(function (group) { return group.date === state.focus; }) : state.groups;
        DayStream.render(host, groups, function (item) { return renderTool(item, practices); }, '<p class="empty">这一天还没有要决定的工具。</p>');
      }
      draw();
      DayStream.bindSelect(document.getElementById("dayJump"), function (value) {
        state.focus = value || "";
        draw();
      });
    }).catch(function () {
      var host = document.getElementById("stream");
      if (host) host.innerHTML = '<p class="empty">工具决策暂时打不开。</p>';
    });
  }

  load();
})();
