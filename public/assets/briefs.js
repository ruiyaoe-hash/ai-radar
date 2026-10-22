/* 最新动态：按日归档里的事件卡片，加上还没进归档的事实短讯。 */
(function () {
  "use strict";

  var state = { span: "7", lens: "all", evidence: "all", events: [], briefs: [] };

  function beijingToday() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).format(new Date());
  }

  function addDays(dateStr, n) {
    var parts = dateStr.split("-").map(Number);
    var dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
    dt.setUTCDate(dt.getUTCDate() + n);
    return dt.toISOString().slice(0, 10);
  }

  function normUrl(url) {
    return String(url || "").trim().replace(/\/+$/, "").toLowerCase();
  }

  function inSpan(date) {
    if (state.span === "all") return true;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date || "")) return false;
    var today = beijingToday();
    var start = addDays(today, state.span === "3" ? -2 : -6);
    return date >= start && date <= today;
  }

  function eventUrls(it) {
    var urls = [];
    if (it.url) urls.push(normUrl(it.url));
    (it.sources || []).forEach(function (source) {
      if (source && source.url) urls.push(normUrl(source.url));
    });
    return urls;
  }

  function bindChips(id, attr, apply) {
    var bar = document.getElementById(id);
    if (!bar) return;
    bar.addEventListener("click", function (event) {
      var button = event.target.closest("[" + attr + "]");
      if (!button) return;
      Array.prototype.forEach.call(bar.querySelectorAll(".chip"), function (el) {
        el.classList.remove("on");
      });
      button.classList.add("on");
      apply(button.getAttribute(attr));
      render();
    });
  }

  function render() {
    var host = document.getElementById("stream");
    if (!host || !window.Radar) return;
    var urls = {};
    state.events.forEach(function (it) {
      eventUrls(it).forEach(function (url) {
        if (url) urls[url] = true;
      });
    });
    var events = state.events.filter(function (it) {
      if (!inSpan(it.date)) return false;
      if (state.lens !== "all" && it.lens !== state.lens) return false;
      if (state.evidence !== "all" && Radar.evidenceOf(it).key !== state.evidence) return false;
      return true;
    });
    var briefs = state.briefs.filter(function (item) {
      if (urls[normUrl(item.url)]) return false;
      if (!inSpan(item.date)) return false;
      if (state.lens !== "all" && item.lens !== state.lens) return false;
      if (state.evidence !== "all") return false;
      return true;
    });
    var byDate = {};
    function add(date, html) {
      var key = date || "未知日期";
      if (!byDate[key]) byDate[key] = [];
      byDate[key].push(html);
    }
    events.forEach(function (it) { add(it.date, Radar.renderCard(it, new Set())); });
    briefs.forEach(function (item) { add(item.date, Radar.renderFactCard(item)); });
    var dates = Object.keys(byDate).sort().reverse();
    if (!dates.length) {
      host.innerHTML = '<p class="empty">这个范围里还没有动态。可以把时间改成全部，或先看<a href="./today.html">今日重点</a>。</p>';
      return;
    }
    host.innerHTML = dates.map(function (date) {
      return '<section><div class="day"><span>' + Radar.esc(Radar.formatDay(date)) + '</span><span class="count">' + byDate[date].length + ' 条</span></div>' + byDate[date].join("") + '</section>';
    }).join("");
    Radar.scrollToHash();
  }

  function loadJson(path) {
    return fetch(path + "?" + Date.now()).then(function (res) {
      if (!res.ok) throw new Error(path);
      return res.json();
    });
  }

  function load() {
    loadJson("./archive/index.json").then(function (index) {
      var dates = (index.dates || []).map(function (row) { return row.date; }).filter(Boolean);
      return Promise.all(dates.map(function (date) {
        return loadJson("./archive/" + date + ".json").then(function (day) {
          return day.items || [];
        }).catch(function () { return []; });
      }));
    }).catch(function () { return []; }).then(function (packs) {
      state.events = packs.reduce(function (all, items) { return all.concat(items); }, []);
      return loadJson("./briefs.json").catch(function () { return { items: [] }; });
    }).then(function (data) {
      state.briefs = (data.items || []).slice();
      var stamp = document.getElementById("updated");
      if (stamp && data.updated) stamp.textContent = "最近更新 " + data.updated;
      render();
    }).catch(function () {
      var host = document.getElementById("stream");
      if (host) host.innerHTML = '<p class="empty">动态还没准备好，稍后再来。今天最该拍板的几条在<a href="./today.html">今日重点</a>。</p>';
    });
  }

  bindChips("spanFilters", "data-span", function (value) { state.span = value || "7"; });
  bindChips("lensFilters", "data-type", function (value) { state.lens = value || "all"; });
  bindChips("evidenceFilters", "data-evidence", function (value) { state.evidence = value || "all"; });
  load();
})();
