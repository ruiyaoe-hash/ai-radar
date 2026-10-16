/* 只允许 http/https，以及站内相对路径（./、../、/、?、#、无协议的路径）。
   不按主机名过滤：HN、Reddit、GitHub、实验室博客都要能打开。
   拒绝 javascript:、data:、vbscript:、协议相对的 //host，以及带引号或空白的字符串。
   URL 解析会丢掉 scheme 里的制表符，所以先看解析后的协议，再决定是否放行。 */
(function (global) {
  function safeHref(url) {
    const raw = String(url == null ? "" : url).replace(/^\uFEFF/, "").trim();
    if (!raw) return "";
    if (/[\u0000-\u001F\u007F\s<>"'`\\]/.test(raw)) return "";
    if (raw.startsWith("//")) return "";
    let parsed;
    try {
      parsed = new URL(raw, "https://radar.invalid/");
    } catch (err) {
      return "";
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    if (/^[a-zA-Z][a-zA-Z+\-.]*:/.test(raw)) {
      if (!/^https?:\/\//i.test(raw)) return "";
      return parsed.href;
    }
    return raw;
  }

  global.safeHref = safeHref;
})(window);
