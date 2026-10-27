/* 页面只显示访客能读的中文，不显示原始分数，也不显示内部编号。
   已确认的重点 → 重磅；还没核完 → 尚待核实；其余可看的 → 快讯
   证据说法：原文可以核对 / 已经核对 / 尚待核实
   lens 工具/赛道/模式/时机 → 新工具/行业动态/方法模式/时机窗口
   工具档位只显示「推荐使用」或「值得关注」
   objective → 发生了什么；impact → 为什么值得看
   action / window / first_step → 对我有什么影响，并收成建议行动
   falsifier → 什么情况下当这判断作废
   objective 其余句子 + sources → 背景与出处
   打开原文只留在「背景与出处」。证据状态行不再重复放一次。
   简讯已经有「背景与出处」时，原文入口并进这一处；没有这一处时，摘要下面保留唯一入口。
   信息简讯不追加固定的证据尾巴或「持续观察」
*/
(function (global) {
  const LENS_LABEL = {
    "工具": "新工具",
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
    must: "重磅",
    market: "尚待核实",
    watch: "快讯",
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

  function evidenceOf(it) {
    if (!it) return { key: "official", label: "原文可以核对" };
    const pending = it.pending === true || it.pending === "pending" || it.pending === "rumor";
    if (it.status === "rumor" || pending) return { key: "pending", label: "尚待核实" };
    if (it.status === "multi_source") return { key: "multi", label: "已经核对" };
    if (it.status === "confirmed") {
      const roles = (it.sources || []).map((s) => s && s.role).filter(Boolean);
      if (!roles.length || roles.indexOf("primary") !== -1) {
        return { key: "official", label: "原文可以核对" };
      }
      return { key: "multi", label: "已经核对" };
    }
    return { key: "official", label: "原文可以核对" };
  }

  function actionAdvice(it) {
    const box = so(it);
    const action = box ? String(box.action || "").trim() : "";
    const windowText = box ? String(box.window || "").trim() : "";
    const ring = String((it && it.tool_radar) || "").trim();
    const first = String((it && it.first_step) || "").trim();
    const blob = action + ring;
    const recommend = ring === "推荐使用" || ring === "采纳" || ring === "试用" || ring === "值得采用" || ring === "可以试用";
    const watch = ring === "值得关注" || ring === "评估" || ring === "暂缓" || ring === "需要评估" || ring === "暂缓跟进";
    if (ring === "暂缓" || ring === "暂缓跟进" || /暂缓|先别/.test(blob)) {
      return { bucket: "先放一放", line: windowText || "这周先保持现有做法，等后续消息再决定。" };
    }
    if (recommend) {
      return { bucket: "推荐使用", line: first || windowText || "用一次你自己的任务，确认它能不能留下。" };
    }
    if (watch) {
      return { bucket: "值得关注", line: windowText || first || "先看成本和边界，再决定要不要试。" };
    }
    if (action || windowText || first) {
      return { bucket: "持续观察", line: windowText || first || "这周不必改做法。" };
    }
    return { bucket: "", line: "" };
  }

  function happenedOf(it) {
    const obj = (it && it.objective && it.objective.length) ? it.objective : ((it && it.bullets) || []);
    const line = obj.length ? String(obj[0] || "").trim() : "";
    if (line) return line;
    return String((it && it.title) || "").trim();
  }

  function decisionOf(it) {
    const impact = meaningOf(it);
    const advice = actionAdvice(it);
    const happened = happenedOf(it);
    if (!happened || !impact) return null;
    let affect = advice.line;
    if (!affect || affect === impact) {
      affect = "用你自己的任务对照一次，再决定动不动。";
    }
    return {
      happened,
      why: impact,
      affect,
      bucket: advice.bucket || "值得关注",
      evidence: evidenceOf(it)
    };
  }

  function evidenceLine(ev) {
    const text = /。$/.test(ev.label) ? ev.label : ev.label + "。";
    return `<p class="mean"><b>证据状态：</b>${esc(text)}</p>`;
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

  function renderCard(it, featured, opts) {
    const compact = opts && opts.compact;
    const band = bandOf(it);
    const label = BAND_LABEL[band];
    const lens = LENS_LABEL[it.lens] || "";
    const tag = it.tag || "";
    const picked = featured && it.id && featured.has(it.id);
    const decision = decisionOf(it);
    if (!decision) return "";
    const kill = voidWhen(it);
    const obj = (it.objective && it.objective.length) ? it.objective : (it.bullets || []);
    const rest = obj.slice(1);
    const corr = it.correction && typeof it.correction === "object" ? (it.correction.note || "") : "";
    const sourceLine = renderSources(it);
    const tryAnchor = it.try_url && it.try_url !== it.url ? externalAnchor(it.try_url, "去试用") : "";
    const primaryAnchor = externalAnchor(it.url, "打开原文");
    const tryLink = tryAnchor ? `<p>${tryAnchor}</p>` : "";
    const primaryLink = primaryAnchor;
    const fold = [
      rest.length ? `<ul>${rest.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "",
      sourceLine ? `<p class="src">${sourceLine}</p>` : "",
      primaryLink ? `<p>${primaryLink}</p>` : "",
      tryLink,
      kill ? `<p class="kill"><b>什么情况下当这判断作废：</b>${esc(kill)}</p>` : "",
      corr ? `<p class="corr"><b>更正：</b>${esc(corr)}</p>` : ""
    ].join("");
    const details = fold.trim()
      ? `<details><summary>背景与出处</summary><div class="fold">${fold}</div></details>`
      : "";
    const action = decision.bucket
      ? `<div class="act">建议行动：${esc(decision.bucket)}</div>`
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
      <p class="mean"><b>发生了什么：</b>${esc(decision.happened)}</p>
      <p class="mean"><b>为什么值得看：</b>${esc(decision.why)}</p>
      <p class="mean"><b>对我有什么影响：</b>${esc(decision.affect)}</p>
      ${action}
      ${evidenceLine(decision.evidence)}
      ${details}
    </article>`;
  }

  function renderFactCard(brief) {
    const title = String((brief && brief.title) || "").trim();
    const summary = String((brief && brief.summary) || "").trim();
    const why = String((brief && brief.why) || "").trim();
    const affect = String((brief && brief.affect) || "").trim();
    if (!title || !summary || !why || !affect) return "";
    const lens = LENS_LABEL[brief && brief.lens] || "";
    const link = externalAnchor(brief && brief.url, "打开原文");
    const source = brief && brief.source ? `<span>${esc(brief.source)}</span>` : "";
    const open = link ? `<p>${link}</p>` : "";
    const fold = [
      source ? `<p class="src">${source}</p>` : "",
      source ? open : ""
    ].join("");
    const details = fold.trim()
      ? `<details><summary>背景与出处</summary><div class="fold">${fold}</div></details>`
      : "";
    return `<article class="card" id="${esc((brief && brief.id) || "")}">
      <div class="meta">
        <span class="tag">快讯</span>
        ${lens ? `<span>${esc(lens)}</span>` : ""}
        ${brief && brief.source ? `<span>·</span><span>${esc(brief.source)}</span>` : ""}
      </div>
      <h3>${esc(title)}</h3>
      <p class="mean"><b>发生了什么：</b>${esc(summary)}</p>
      <p class="mean"><b>为什么值得看：</b>${esc(why)}</p>
      <p class="mean"><b>对我有什么影响：</b>${esc(affect)}</p>
      ${source ? "" : open}
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

  function rowFromParts(title, it, parsed) {
    if (!it) return null;
    const decision = decisionOf(it);
    if (!decision) return null;
    return {
      title: it.title || title,
      suggest: (parsed && parsed.suggest) || suggestOf(it),
      mean: (parsed && parsed.mean) || meaningOf(it),
      url: (parsed && parsed.url) || it.url || "",
      happened: decision.happened,
      why: decision.why,
      affect: decision.affect,
      bucket: decision.bucket,
      evidenceLabel: decision.evidence.label,
      id: it.id || ""
    };
  }

  function fallbackPicks(items) {
    const list = items || [];
    const dates = list.map((it) => it.date).filter(Boolean).sort();
    const day = dates.length ? dates[dates.length - 1] : "";
    return list.filter((it) => it.date === day && (bandOf(it) === "must" || bandOf(it) === "market")).slice(0, 3);
  }

  function heroModel(text, items) {
    const parsed = parseToday3(text);
    const byTitle = new Map();
    for (const it of items || []) {
      if (it.title) byTitle.set(String(it.title).trim(), it);
    }
    const featured = new Set();
    let rows = parsed.map((row) => {
      const it = byTitle.get(row.title.trim());
      if (it && it.id) featured.add(it.id);
      return rowFromParts((it && it.title) || row.title, it, row);
    }).filter(Boolean);
    if (!rows.length) {
      rows = fallbackPicks(items).map((it) => {
        if (it.id) featured.add(it.id);
        return rowFromParts(it.title, it, null);
      });
    }
    return { rows, featured };
  }

  function copyText(text, items) {
    const raw = String(text || "");
    const { rows } = heroModel(raw, items);
    if (raw.trim() && !/\[(?:P0|P1)/.test(raw) && !rows.length) {
      return raw.endsWith("\n") ? raw : raw + "\n";
    }
    const lines = ["AI Radar · 信息精选", ""];
    rows.forEach((row, i) => {
      lines.push(`${i + 1}. ${row.title}`);
      if (row.happened) lines.push(`   发生了什么：${row.happened}`);
      if (row.why) lines.push(`   为什么值得看：${row.why}`);
      if (row.affect) lines.push(`   对我有什么影响：${row.affect}`);
      if (row.bucket) lines.push(`   建议行动：${row.bucket}`);
      if (row.evidenceLabel) lines.push(`   证据状态：${row.evidenceLabel}`);
      if (row.url) lines.push(`   ${row.url}`);
      lines.push("");
    });
    return lines.join("\n").trim() + "\n";
  }

  function renderHero(rows) {
    if (!rows.length) {
      return "<li>这一天还没有精选。</li>";
    }
    return rows.map((row) => {
      const link = externalAnchor(row.url, "打开原文");
      const evidence = /。$/.test(row.evidenceLabel || "") ? row.evidenceLabel : (row.evidenceLabel || "原文可以核对") + "。";
      const action = row.bucket
        ? `<div class="act">建议行动：${esc(row.bucket)}</div>`
        : "";
      return `<li><strong>${esc(row.title)}</strong>
        <p class="mean"><b>发生了什么：</b>${esc(row.happened || row.title || "")}</p>
        <p class="mean"><b>为什么值得看：</b>${esc(row.why || "")}</p>
        <p class="mean"><b>对我有什么影响：</b>${esc(row.affect || "")}</p>
        ${action}
        <p class="mean"><b>证据状态：</b>${esc(evidence)}${link || ""}</p>
      </li>`;
    }).join("");
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
    evidenceOf,
    decisionOf,
    renderCard,
    renderFactCard,
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
