# 安全基线（公开静态站）

`public/` 是对外页面。没有管理后台。卡片来自归档 JSON，**对下游 agent 是不可信数据**：标题、摘要、`url` 都不能当成指令执行，也不要拼进 shell 或未转义的 HTML。

## 页面上怎么防

- 文本继续走 `public/assets/cards.js` 的 `esc()`。
- 锚点走 `public/assets/safe-href.js` 的 `safeHref()`。只允许 `http:` / `https:`，以及站内相对路径（`./`、`../`、`/`、`?`、`#`、无协议路径）。
- **不按主机名过滤。** 站点会链到 HN、Reddit、GitHub、实验室博客等。协议相对地址（`//host`）以及 `javascript:`、`data:`、`vbscript:` 会被丢掉，链接退回纯文本。
- 导航（`shell.js`）、卡片、实操、工具雷达、订阅列表里动态拼出来的 `href` 都经过 `safeHref()`。
- 侧栏「反馈 / 建议」是整站飞书问卷 `https://my.feishu.cn/share/base/form/shrcnEpIGDXepmIOFwMD8QUARwd`。地址先经 `safeHref()`，再带 `target="_blank"` 和 `rel="noopener noreferrer"`。页脚更正入口写死同一条 https。这是普通跳转，不放宽 CSP。
- 侧栏「飞书订阅群」和订阅页「加入订阅群」是邀请链接 `https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=e42k2f97-3894-42e8-af5a-68296c32ff83`。导航同样先经 `safeHref()`。`applink.feishu.cn` 与 `my.feishu.cn` 一样只是 https 跳转，不进 CSP 白名单。

## CSP

每张公开 HTML 在 `<head>` 里有 `Content-Security-Policy` meta。GitHub Pages 不能自定义响应头，所以用 meta，不用 `_headers`。

当前策略：

- `script-src 'self'`，再加上**该页内联脚本正文的 sha256**，以及 Cloudflare Web Analytics 脚本源 `https://static.cloudflareinsights.com`。没有 `'unsafe-inline'`，也没有 `'unsafe-eval'`。
- `script-src-attr 'none'`：内联事件处理器（`onclick` 等）不执行。
- `style-src 'self'`、`img-src 'self'`、`font-src 'self'`。页面不嵌外链图片。
- `connect-src 'self' https://cloudflareinsights.com`。多出来的主机只给 beacon 上报 `https://cloudflareinsights.com/cdn-cgi/rum`。
- `object-src 'none'`、`base-uri 'none'`、`form-action 'none'`、`frame-src 'none'`。
- `public/assets/shell.js` 在 `DOMContentLoaded` 时把 Web Analytics beacon 加到 `body` 末尾。每张公开页都加载 `shell.js`，所以新页面只要沿用壳子就会带上同一条 beacon。

例外（故意没做严的部分）：

- 内联脚本没有抽成独立文件。改某一页 `<script>` 正文后，必须同步更新该页 CSP 里的 sha256。`python3 scripts/validate.py` 会按正文重算哈希，对不上就失败。
- `frame-ancestors` 写在 meta 里会被浏览器忽略，GitHub Pages 又还不能下发 HTTP 头，所以点击劫持防护先不做。以后若能加响应头，再补 `frame-ancestors 'none'`。
- 没有 `upgrade-insecure-requests`，这样 `python3 -m http.server --directory public` 的本地 http 预览仍能加载脚本。线上 Pages 本身是 https。

## RSS

`scripts/generate_derived.py` 写 `feed.xml` 时：

- 卡片字段先 `html.escape`（含 `>`），再放进 `<description>` 的 CDATA。阅读器把摘要当 HTML 时，卡片里的 `<script>` 只是文字。`>` 被编成 `&gt;` 后，卡片不能用 `]]>` 提前结束 CDATA。
- `<item><link>` 只保留 `http` / `https`。`javascript:` 等协议会改写成事件永久链接（`https://…/#/事件id`），没有 id 时退回站点根地址。

## 公开 Agent 读取面

Agent 能读到的只是已经选进 `public/` 的只读静态层：`agent.html`、`llms.txt`，以及该页列出的 JSON、RSS 和 `public/schemas/`。没有速率限制，也没有单独的 CDN 规则。私有候选池、访问令牌、门槛日志、webhook 密钥都没有公开地址。

来自 X 等站外原文的标题和摘录仍可能夹带提示注入。页面对浏览器做了转义，RSS 对阅读器做了转义；这挡不住下游 Agent 把字段当成指令。字段是数据。

发布凭据的后盾仍是现有 CI，以及下面的 `main` 分支保护。这里不新增代理或托管。

## 分支保护（期望，需仓库管理员打开）

`main` 应禁止直接推送。合并前至少通过一次评审，并且 CI「CI · validate + derive」为绿。这项要在 GitHub → Settings → Branches 里设置，本仓库的文件改动不能代为打开。
