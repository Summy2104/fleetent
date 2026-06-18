# Design — fix-slack-file-download-follow-redirects

## 问题精确化

`_download_attachments(files, bot_token)`（`src/fleetent/im_gateway/slack.py` ~285）对每个入站 file：

1. `mime` 以 `image/` 开头 → 图片分支（~307-315）：`client.get(url)` → `raise_for_status()` → `out.append((content, mime))`。
2. 否则 → 文件分支（~316-342）：size 上限检查 → `client.get(url)` → `raise_for_status()` → 上限复核 → `out.append(FileAttachment(data, mime, filename))`；任一 `httpx.HTTPError` → warning + `data=None` 占位项。

两分支共用同一个 `async with httpx.AsyncClient() as client`（~301），**未传 `follow_redirects`**（默认 False）。

**缺陷一（302）**：Slack 对 PDF 等类型把 `url_private` 以 302 跳到 `slack-files.com/files-pri-safe/...?c=<票>`。httpx 默认不跟随，且 `raise_for_status()` 对 3xx 抛 `HTTPStatusError`（新版行为）→ 文件分支降级占位、图片分支 warning 跳过。哪些类型走 302 是 Slack 未文档化的服务端行为，不可枚举特判。

**缺陷二（HTML）**：token scope 不足 / 文件无权限时，Slack 返回 200 + `text/html` 的登录/错误页。现状两分支都不看 content-type，会把 HTML 当文件字节缓存。

## 决策

### D1. 跟随重定向：在 client 构造处一次性打开，不按类型特判
`httpx.AsyncClient()` → `httpx.AsyncClient(follow_redirects=True)`。

- 图片分支与文件分支共用此 client，一处改、两处受益。
- **为什么不按文件类型判**：Slack 官方未文档化类型→302 策略，可对任意类型返回、可随时变；按类型特判脆弱且必然漏。无条件跟随是唯一稳健解，也与官方「客户端需处理重定向」一致。
- **token 安全**：302 目标 `slack-files.com` 与 `files.slack.com` 异域，httpx 跨域重定向**自动剥除 `Authorization` 头**；目标 URL 自带 `?c=<签名票>` 鉴权，不需要 Bearer。故跟随重定向不会把 bot token 泄露到新域。
- **对 200 直出无副作用**：无重定向时 `follow_redirects` 不改变任何行为。

### D2. HTML 兜底：成功响应后判 content-type，两分支各自降级
`raise_for_status()` 通过后，取 `resp.headers.get("content-type", "")`，若以 `text/html` 开头（用 `.split(";")[0].strip().startswith("text/html")` 容忍 `; charset=...`）：

- **文件分支**：不取 `resp.content`，记 warning（`slack_file_download_failed`，error 注明 content-type=text/html），`out.append(FileAttachment(data=None, mime, filename, note="文件下载失败"))` —— 复用既有失败降级路径，note 文案与现有一致（或细化提示 token/权限）。
- **图片分支**：记 warning（`slack_image_download_failed`），`continue` 跳过 —— 与图片下载失败的既有处理一致。

照 hermes 的语义（`slack.py:3663-3669`「Slack returned HTML instead of media; check bot token scopes and file permissions」），但落进 fleetent 现有的「降级占位 / 跳过」结构，不抛异常中断消息处理。

### D3. 不引入 retry / 不改 url_private（scope 边界）
hermes 还有 3 次 timeout/429 重试与 `url_private_download` 优先。本 change **不含**：

- retry：扩大 diff 与测试面，且当前 bug 与重试无关（302/HTML 重试也不会变）；留作后续。
- `url_private_download`：会改下载语义且现有 `im-file-attachment` spec 明确用 `url_private`；本 change 不动该语义。

## 测试策略（unit，复用现有 _FakeClient 模式）

现有 `tests/unit/test_slack_file_download.py` 用 `patch("httpx.AsyncClient", return_value=client)` 注入 `_FakeClient`。新增：

1. **跟随重定向参数**：用 `side_effect` 捕获 `httpx.AsyncClient(**kwargs)` 的 kwargs，断言 `follow_redirects is True`（构造一个返回 `_FakeClient` 的捕获器）。这是「无条件跟随」的契约点——不能靠真实 302（unit 不发网络）。
2. **302 不再降级**：`_FakeClient` 的 handler 返回带正常字节 + 非 html content-type 的响应，模拟「跟随后拿到字节」→ 断言文件分支得到 `data=<字节>`（间接验证 follow_redirects 生效路径不被 raise_for_status 截断；与 1 互补）。
3. **HTML 兜底（文件）**：handler 返回 content-type=`text/html; charset=utf-8` 的响应 → 断言 `out[0].data is None` 且 `note != ""`，且**未**把 HTML body 当字节。
4. **HTML 兜底（图片）**：图片 url 返回 text/html → 断言该图片被跳过（不进 out，或 out 不含其字节）。
5. 现有 4 个用例必须保持绿（`_Resp` 需补一个空/默认 `headers`，使 content-type 取值不报错）。

> `_Resp` 当前无 `.headers`；实现读 `resp.headers.get(...)` 后，测试的 `_Resp` 需加 `headers={}`（或 `{"content-type": "..."}`）。这是测试夹具的最小适配，不改产线逻辑边界。

## 可观测信号

修复后，对 PDF 等 302 类型：journal 不再出现 `slack_file_download_failed ... Redirect response '302 Found'`，附件 `data` 非空、`note` 为空，模型可正常读到 PDF。对 token/权限问题：出现新的 `content-type=text/html` warning，附件降级占位（而非缓存 HTML）。
