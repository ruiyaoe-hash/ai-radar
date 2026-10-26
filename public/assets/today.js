/* 信息精选：按上海日历日往下排。硬门槛选出的条目优先；某一天一条都没有时，当天最强的一条工具或简讯会顶上。 */
(function () {
  "use strict";

  var state = { groups: [], focus: "" };

  function loadJson(path) {
    return fetch(path + "?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error(path);
      return res.json();
    });
  }

  function visibleGroups() {
    if (!state.focus) return state.groups;
    return state.groups.filter(function (group) { return group.date === state.focus; });
  }

  function render() {
    var host = document.getElementById("feed");
    if (!host || !window.DayStream || !window.Radar) return;
    DayStream.render(
      host,
      visibleGroups(),
      function (item) { return Radar.renderCard(item, new Set()); },
      '<p class="empty">这一天还没有精选。可以换一天，或先看<a href="./briefs.html">信息简讯</a>。</p>'
    );
    if (window.Radar.scrollToHash) Radar.scrollToHash();
  }

  function load() {
    loadJson("./picks.json").then(function (data) {
      var days = Array.isArray(data.days) ? data.days : [];
      state.groups = days.map(function (day) {
        return { date: day.date, items: day.items || [] };
      }).filter(function (group) { return group.date; });
      var stamp = document.getElementById("updated");
      if (stamp && data.updated) stamp.textContent = "最近更新 " + data.updated;
      DayStream.fillSelect(document.getElementById("dayJump"), state.groups.map(function (group) { return group.date; }));
      render();
    }).catch(function () {
      var host = document.getElementById("feed");
      if (host) host.innerHTML = '<p class="empty">信息精选暂时打不开。可以先看<a href="./briefs.html">信息简讯</a>。</p>';
    });
  }

  var copy = document.getElementById("copyToday");
  if (copy) {
    copy.addEventListener("click", function () {
      var newest = state.groups[0];
      var lines = ["AI Radar · 信息精选", ""];
      ((newest && newest.items) || []).forEach(function (item, index) {
        lines.push((index + 1) + ". " + (item.title || ""));
        var impact = item.so_what && item.so_what.impact;
        if (impact) lines.push("   为什么值得看：" + impact);
        if (item.url) lines.push("   " + item.url);
        lines.push("");
      });
      var text = lines.join("\n").trim() + "\n";
      var fallback = document.getElementById("today3fallback");
      var done = function (label) {
        copy.textContent = label;
        setTimeout(function () { copy.textContent = "复制最新一天"; }, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done("已复制"); }).catch(function () {
          if (fallback) {
            fallback.hidden = false;
            fallback.textContent = text;
          }
          done("请手动复制");
        });
      } else {
        if (fallback) {
          fallback.hidden = false;
          fallback.textContent = text;
        }
        done("请手动复制");
      }
    });
  }

  DayStream.bindSelect(document.getElementById("dayJump"), function (value) {
    state.focus = value || "";
    render();
  });
  load();
})();
