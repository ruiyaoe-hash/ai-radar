/* 按上海日历日往下排的时间流。信息精选、信息简讯、工具决策共用。 */
(function (global) {
  "use strict";

  function calendarLabel(dateStr) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr || "")) return dateStr || "";
    var parts = dateStr.split("-");
    return parts[0] + "年" + Number(parts[1]) + "月" + Number(parts[2]) + "日";
  }

  function groupByDate(items, dateOf) {
    var map = {};
    (items || []).forEach(function (item) {
      var date = dateOf(item) || "";
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
      if (!map[date]) map[date] = [];
      map[date].push(item);
    });
    return Object.keys(map).sort().reverse().map(function (date) {
      return { date: date, items: map[date] };
    });
  }

  function fillSelect(select, dates) {
    if (!select) return;
    var current = select.value;
    var options = ['<option value="">全部日期</option>'].concat(dates.map(function (date) {
      return '<option value="' + date + '">' + calendarLabel(date) + "</option>";
    }));
    select.innerHTML = options.join("");
    if (current && dates.indexOf(current) !== -1) select.value = current;
  }

  function render(host, groups, renderItem, emptyHtml) {
    if (!host) return;
    var html = (groups || []).map(function (group) {
      var body = group.items.map(renderItem).filter(Boolean).join("");
      if (!body) return "";
      return '<section id="day-' + group.date + '"><div class="day"><span>' + calendarLabel(group.date) + '</span><span class="count">' + group.items.length + " 条</span></div>" + body + "</section>";
    }).filter(Boolean).join("");
    host.innerHTML = html || emptyHtml;
  }

  function bindSelect(select, onChange) {
    if (!select) return;
    select.addEventListener("change", function () {
      var value = select.value;
      if (!value) {
        onChange("");
        return;
      }
      var target = document.getElementById("day-" + value);
      if (target && target.scrollIntoView) target.scrollIntoView({ behavior: "smooth", block: "start" });
      onChange(value);
    });
  }

  global.DayStream = {
    calendarLabel: calendarLabel,
    groupByDate: groupByDate,
    fillSelect: fillSelect,
    render: render,
    bindSelect: bindSelect
  };
})(window);
