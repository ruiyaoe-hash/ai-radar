/* 页面只显示中文叫法。内部字段在这里读取：
   priority=P0 且 rumor/pending → 市场信号
   priority=P0 且非 rumor/pending → 今日必看
   priority=P1 → 重点关注
   lens 工具/赛道/模式/时机 → 试用工具/行业动态/方法模式/时机窗口
   impact → 对你意味着什么；action+window → 建议
   falsifier → 什么情况下当这判断作废
   objective+sources → 背景与出处
*/
(function (global) {
  const LENS_LABEL = {
    "工具": "试用工具",
    "赛道": "行业动态",
    "模式": "方法模式",
    "时机": "时机窗口"
  };
  const ROLE_LABEL = { primary: "一手", analysis: "解读", report: "转述" };

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  const safeHref = global.safeHref;
  if (typeof safeHref !== "function") {
    throw new Error("safe-href.js must load before cards.js");
  }

  function externalAnchor(url, labelHtml) {
    const href = safeHref(url);
    if (!href) return "";
    return `<a href="${esc(href)}" target="_blank" rel="noopener">${labelHtml}</a>`;
  }

  function isMarket(it) {
    if (!it || it.priority !== "P0") return false;
    if (it.status === "rumor") return true;
    const pending = it.pending;
    return pending === true || pending === "pending" || pending === "rumor";
  }

  function bandOf(it) {
    if (isMarket(it)) return "market";
    if (it && it.priority === "P0") return "must";
    if (it && it.priority === "P1") return "watch";
    return "other";
  }

  const BAND_LABEL = {
    must: "今日必看",
    market: "市场信号",
    watch: "重点关注",
    other: ""
  };
  const BAND_CLASS = { must: "must", market: "rumor", watch: "watch", other: "" };

  function weekdayCN(dateStr) {
    const d = new Date(dateStr + "T12:00:00+08:00");
    return ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][d.getDay()];
  }

  function formatDay(dateStr) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr || "")) return dateStr || "";
    const parts = dateStr.split("-");
    return `${Number(parts[1])} 月 ${Number(parts[2])} 日 · ${weekdayCN(dateStr)}`;
  }

  function so(it) {
    return it && it.so_what && typeof it.so_what === "object" ? it.so_what : null;
  }

  function meaningOf(it) {
    const box = so(it);
    if (box && String(box.impact || "").trim()) return String(box.impact).trim();
    const jud = (it && it.judgment) || [];
    if (jud.length) return jud.join(" ");
    return "";
  }

  function suggestOf(it) {
    const box = so(it);
    if (!box) return "";
    return [box.action, box.window].map((x) => String(x || "").trim()).filter(Boolean).join(" · ");
  }

  function voidWhen(it) {
    const box = so(it);
    return box ? String(box.falsifier || "").trim() : "";
  }

  function renderSources(it) {
    const srcs = (it && it.sources) || [];
    if (!srcs.length) {
      return it && it.handle ? `<span>${esc(it.handle)}</span>` : "";
    }
    return srcs.map((s) => {
      const role = ROLE_LABEL[s.role] || "";
      const name = esc(s.handle || "");
      const inner = role ? `${name} · ${role}` : name;
      return externalAnchor(s.url, inner) || `<span>${inner}</span>`;
    }).join("");
  }

  function renderCard(it, featured) {
    const band = bandOf(it);
    const label = BAND_LABEL[band];
    const lens = LENS_LABEL[it.lens] || "";
    const tag = it.tag || "";
    const picked = featured && it.id && featured.has(it.id);
    const mean = meaningOf(it);
    const suggest = suggestOf(it);
    const kill = voidWhen(it);
    const obj = (it.objective && it.objective.length) ? it.objective : (it.bullets || []);
    const corr = it.correction && typeof it.correction === "object" ? (it.correction.note || "") : "";
    const sourceLine = renderSources(it);
    const tryAnchor = it.try_url && it.try_url !== it.url ? externalAnchor(it.try_url, "去试用") : "";
    const primaryAnchor = externalAnchor(it.url, "打开原文");
    const tryLink = tryAnchor ? `<p>${tryAnchor}</p>` : "";
    const primaryLink = primaryAnchor ? `<p>${primaryAnchor}</p>` : "";
    const fold = [
      obj.length ? `<ul>${obj.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "",
      sourceLine ? `<p class="src">${sourceLine}</p>` : "",
      primaryLink,
      tryLink,
      kill ? `<p class="kill"><b>什么情况下当这判断作废：</b>${esc(kill)}</p>` : "",
      corr ? `<p class="corr"><b>更正：</b>${esc(corr)}</p>` : ""
    ].join("");
    const details = fold.trim()
      ? `<details><summary>背景与出处</summary><div class="fold">${fold}</div></details>`
      : "";
    return `<article class="card" id="${esc(it.id || "")}">
      <div class="meta">
        ${picked ? '<span class="pill"><span class="dot"></span>精选</span>' : ""}
        ${label ? `<span class="tag ${BAND_CLASS[band]}">${label}</span>` : ""}
        ${tag ? `<span class="tag">${esc(tag)}</span>` : ""}
        ${lens ? `<span>${esc(lens)}</span>` : ""}
        ${it.handle ? `<span>·</span><span>${esc(it.handle)}</span>` : ""}
      </div>
      <h3>${esc(it.title || "")}</h3>
      ${mean ? `<p class="mean"><b>对你意味着什么：</b>${esc(mean)}</p>` : ""}
      ${suggest ? `<div class="act">建议：${esc(suggest)}</div>` : ""}
      ${details}
    </article>`;
  }

  function applyFilter(list, band, lens) {
    return (list || []).filter((it) => {
      if (lens && lens !== "all" && it.lens !== lens) return false;
      if (!band || band === "all") return true;
      return bandOf(it) === band;
    });
  }

  function groupByDate(list) {
    const map = new Map();
    for (const it of list) {
      const d = it.date || "未知日期";
      if (!map.has(d)) map.set(d, []);
      map.get(d).push(it);
    }
    return [...map.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])));
  }

  function parseToday3(text) {
    const blocks = [];
    let cur = null;
    for (const line of String(text || "").split(/\n/)) {
      const m = line.match(/^\s*(\d+)\.\s+(?:\[[^\]]*\]\s*)?(.+?)\s*$/);
      if (m) {
        cur = { title: m[2].trim(), suggest: "", mean: "", url: "" };
        blocks.push(cur);
        continue;
      }
      if (!cur) continue;
      const t = line.trim();
      if (!t) continue;
      if (/^建议[:：]/.test(t)) cur.suggest = t.replace(/^建议[:：]\s*/, "");
      else if (/^对你意味着什么/.test(t)) cur.mean = t.replace(/^对你意味着什么[:：]\s*/, "");
      else if (/^https?:\/\//.test(t)) cur.url = t;
      else if (/^[·•\-]/.test(t) && !cur.mean) cur.mean = t.replace(/^[·•\-]\s*/, "");
    }
    return blocks;
  }

  function heroModel(text, items) {
    const parsed = parseToday3(text);
    const byTitle = new Map();
    for (const it of items || []) {
      if (it.title) byTitle.set(String(it.title).trim(), it);
    }
    const featured = new Set();
    const rows = parsed.map((row) => {
      const it = byTitle.get(row.title.trim());
      if (it && it.id) featured.add(it.id);
      return {
        title: (it && it.title) || row.title,
        suggest: row.suggest || (it ? suggestOf(it) : ""),
        mean: row.mean || (it ? meaningOf(it) : ""),
        url: row.url || (it && it.url) || ""
      };
    });
    return { rows, featured };
  }

  function copyText(text, items) {
    const raw = String(text || "");
    if (raw.trim() && !/\[(?:P0|P1)/.test(raw)) {
      return raw.endsWith("\n") ? raw : raw + "\n";
    }
    const { rows } = heroModel(raw, items);
    const lines = ["AI Radar · 今天先做这 3 件", ""];
    rows.forEach((row, i) => {
      lines.push(`${i + 1}. ${row.title}`);
      if (row.mean) lines.push(`   对你意味着什么：${row.mean}`);
      if (row.suggest) lines.push(`   建议：${row.suggest}`);
      if (row.url) lines.push(`   ${row.url}`);
      lines.push("");
    });
    return lines.join("\n").trim() + "\n";
  }

  function renderHero(rows) {
    if (!rows.length) {
      return "<li>今天的三条还没准备好。</li>";
    }
    return rows.map((row) => `<li><strong>${esc(row.title)}</strong>${
      row.suggest ? `<div class="act">建议：${esc(row.suggest)}</div>` : ""
    }</li>`).join("");
  }

  function renderGroups(list, featured) {
    if (!list.length) return '<p class="empty">这一筛选项下暂无内容。</p>';
    return groupByDate(list).map(([date, items]) => `
      <section>
        <div class="day"><span>${esc(formatDay(date))}</span><span class="count">${items.length} 条</span></div>
        ${items.map((it) => renderCard(it, featured)).join("")}
      </section>
    `).join("");
  }

  function scrollToHash() {
    const hash = location.hash.replace(/^#\/?/, "");
    if (!hash) return;
    const el = document.getElementById(hash);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  global.Radar = {
    esc,
    safeHref,
    bandOf,
    LENS_LABEL,
    renderCard,
    applyFilter,
    groupByDate,
    formatDay,
    heroModel,
    copyText,
    renderHero,
    renderGroups,
    scrollToHash
  };
})(window);
