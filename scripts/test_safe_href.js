#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const sandbox = {
  window: {},
  console,
  URL,
  location: { hash: "" },
  document: { getElementById() { return null; } },
};
vm.createContext(sandbox);

function load(rel) {
  const code = fs.readFileSync(path.join(root, rel), "utf8");
  vm.runInContext(code, sandbox, { filename: rel });
}

load("public/assets/safe-href.js");
load("public/assets/cards.js");

const safeHref = sandbox.window.safeHref;
const Radar = sandbox.window.Radar;
if (typeof safeHref !== "function" || Radar.safeHref !== safeHref) {
  console.error("FAIL: safeHref was not exported");
  process.exit(1);
}

let failed = 0;
function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    failed += 1;
  }
}

const allowed = [
  ["https://news.ycombinator.com/item?id=1", "https://news.ycombinator.com/item?id=1"],
  ["https://www.reddit.com/r/MachineLearning/", "https://www.reddit.com/r/MachineLearning/"],
  ["https://github.com/ruiyaoe-hash/ai-radar", "https://github.com/ruiyaoe-hash/ai-radar"],
  ["https://www.anthropic.com/research/x", "https://www.anthropic.com/research/x"],
  [
    "https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd",
    "https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd",
  ],
  ["http://example.com/a", "http://example.com/a"],
  ["HTTP://example.com/a", "http://example.com/a"],
  ["./feed.xml", "./feed.xml"],
  ["../assets/logo.png", "../assets/logo.png"],
  ["/ai-radar/", "/ai-radar/"],
  ["archive/2026-10-13.json", "archive/2026-10-13.json"],
  ["#/evt-1", "#/evt-1"],
  ["?sample=1", "?sample=1"],
];

for (const [input, expect] of allowed) {
  assert(safeHref(input) === expect, `allow ${JSON.stringify(input)} → ${JSON.stringify(safeHref(input))}`);
}

const rejected = [
  "javascript:alert(1)",
  "JAVASCRIPT:alert(1)",
  " javascript:alert(1)",
  "java\tscript:alert(1)",
  "java\nscript:alert(1)",
  "data:text/html,<script>alert(1)</script>",
  "data:text/html;base64,PGgxPmhpPC9oMT4=",
  "vbscript:msgbox(1)",
  "mailto:editor@example.com",
  "ftp://example.com/a",
  "//evil.example/a",
  "https://example.com/a\"onclick=\"alert(1)",
  "https://example.com/a onclick=alert(1)",
  "",
  null,
  undefined,
];

for (const input of rejected) {
  assert(safeHref(input) === "", `reject ${JSON.stringify(input)} → ${JSON.stringify(safeHref(input))}`);
}

const html = Radar.renderCard({
  id: "evt-20261013-xss",
  title: '<img src=x onerror="alert(1)">',
  url: "javascript:alert(1)",
  try_url: "data:text/html,hi",
  handle: "<b>h</b>",
  tag: "<i>t</i>",
  lens: "工具",
  priority: "P0",
  status: "rumor",
  objective: ["<script>alert(1)</script>"],
  sources: [
    { handle: "HN", role: "primary", url: "javascript:alert(2)" },
    { handle: "GH", role: "report", url: "https://github.com/a/b" },
  ],
  so_what: { impact: "<script>i</script>", action: "观察", window: "本周", falsifier: "x" },
  correction: { note: "<b>c</b>" },
}, new Set());

assert(!/href\s*=\s*["']\s*javascript:/i.test(html), "renderCard wrote a javascript: href");
assert(!/href\s*=\s*["']\s*data:/i.test(html), "renderCard wrote a data: href");
assert(!/<script/i.test(html), "renderCard wrote a raw script tag");
assert(html.includes("&lt;script&gt;"), "renderCard did not escape objective text");
assert(html.includes("https://github.com/a/b"), "renderCard dropped a https source");
assert(html.includes("&lt;img"), "renderCard did not escape the title");

if (failed) {
  console.error(`safeHref: ${failed} failed`);
  process.exit(1);
}
console.log(`OK safeHref: ${allowed.length + rejected.length} cases, renderCard blocks bad urls`);
