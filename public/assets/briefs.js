/* 信息简讯：只渲染事实简讯。信息精选里的条目不会出现在这里。 */
(function () {
  "use strict";

  var state = { groups: [], focus: "" };

  function loadJson(path) {
    return fetch(path + "?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error(path);
      return res.json();
    });
  }

  function normUrl(url) {
    return String(url || "").trim().replace(/\/+$/, "").toLowerCase();
  }

  function blockedFrom(picks) {
    var urls = {};
    var ids = {};
    (picks.blocked_urls || []).forEach(function (url) { if (url) urls[normUrl(url)] = true; });
    (picks.blocked_ids || []).forEach(function (id) { if (id) ids[id] = true; });
    (picks.days || []).forEach(function (day) {
      (day.items || []).forEach(function (item) {
        if (item.id) ids[item.id] = true;
        if (item.candidate_id) ids[item.candidate_id] = true;
        if (item.url) urls[normUrl(item.url)] = true;
        (item.sources || []).forEach(function (source) {
          if (source && source.url) urls[normUrl(source.url)] = true;
        });
      });
    });
    return { urls: urls, ids: ids };
  }

  function visibleGroups() {
    if (!state.focus) return state.groups;
    return state.groups.filter(function (group) { return group.date === state.focus; });
  }

  function render() {
    var host = document.getElementById("stream");
    if (!host || !window.DayStream || !window.Radar) return;
    DayStream.render(
      host,
      visibleGroups(),
      function (item) { return Radar.renderFactCard(item); },
      '<p class="empty">这一天还没有简讯。可以换一天，或先看<a href="./today.html">信息精选</a>。</p>'
    );
    if (window.Radar.scrollToHash) Radar.scrollToHash();
  }

  function load() {
    Promise.all([
      loadJson("./briefs.json").catch(function () { return { items: [] }; }),
      loadJson("./picks.json").catch(function () { return { days: [], blocked_urls: [], blocked_ids: [] }; })
    ]).then(function (pair) {
      var data = pair[0];
      var block = blockedFrom(pair[1] || {});
      var items = (data.items || []).filter(function (item) {
        if (item.id && block.ids[item.id]) return false;
        if (item.candidate_id && block.ids[item.candidate_id]) return false;
        if (item.url && block.urls[normUrl(item.url)]) return false;
        return true;
      });
      state.groups = DayStream.groupByDate(items, function (item) { return item.date; });
      var stamp = document.getElementById("updated");
      if (stamp && data.updated) stamp.textContent = "最近更新 " + data.updated;
      DayStream.fillSelect(document.getElementById("dayJump"), state.groups.map(function (group) { return group.date; }));
      render();
    }).catch(function () {
      var host = document.getElementById("stream");
      if (host) host.innerHTML = '<p class="empty">信息简讯暂时打不开。可以先看<a href="./today.html">信息精选</a>。</p>';
    });
  }

  DayStream.bindSelect(document.getElementById("dayJump"), function (value) {
    state.focus = value || "";
    render();
  });
  load();
})();
