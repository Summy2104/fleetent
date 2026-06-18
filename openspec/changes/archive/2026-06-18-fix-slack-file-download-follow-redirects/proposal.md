## Why

入站文件下载对**走 302 跳转的文件类型（如 PDF）100% 失败**。现网实测（2026-06-18 03:29）：用户在 Slack 传 `2025年体检预约流程-v1.0.2.pdf` 要求讲解，agent 记 `slack_file_download_failed`，附件降级为空占位 `note="文件下载失败"`，模型拿不到内容。

根因在 `src/fleetent/im_gateway/slack.py` 的 `_download_attachments`（~285）：

- 下载用 `httpx.AsyncClient()`（~301），**未设 `follow_redirects=True`**（httpx 默认 False）。Slack 对 PDF 等「浏览器内联渲染、可能含活动内容」的类型，把 `url_private`（`files.slack.com/files-pri/...`）以 **302** 跳到沙箱安全域 `slack-files.com/files-pri-safe/...?c=<签名票>`；新版 httpx 的 `raise_for_status()` 对 3xx 同样抛 `HTTPStatusError` → 走 except 分支降级。图片分支（~307）共用同一 client，同样隐患（图片当前恰好 200 直出未踩到）。

- **Slack 官方文档未把「哪些类型走 302」文档化**——这是服务端/CDN 内部行为，可对任意类型返回、可随时变。因此「实测只有 PDF 走 302」不可作为依据；正确做法是**无条件跟随重定向**，不按类型特判。跨域跳转后 httpx 会自动剥掉 `Authorization` 头，而 `slack-files.com` 用 `?c=` 签名票鉴权、不需要 Bearer，故跟随重定向不会泄露 bot token。

- 另一个官方已知坑（bolt-js #2585 / deno-slack-sdk #285）：token scope 不足 / 文件无权限时，Slack 会返回**登录/错误 HTML 页**而非文件字节。现状代码无任何 content-type 兜底，会把这段 HTML 当文件字节缓存、污染下游。

参照实现 `hermes-agent`（`gateway/platforms/slack.py`）两点都做了：所有下载 client 带 `follow_redirects=True`（`_download_slack_file` ~3650 / `_download_slack_file_bytes` ~3706），并在拿到响应后显式判 `content-type: text/html` → 报清晰错误（~3663-3669）。本 change 照此修 fleetent。

## What Changes

仅做两条 correctness 修复，scope 收敛：

- **① 无条件跟随重定向**：`_download_attachments` 的 `httpx.AsyncClient()` 改为 `httpx.AsyncClient(follow_redirects=True)`。图片分支与文件分支共用此 client，一并受益。修复对 200 直出的文件无副作用。
- **② HTML 响应兜底**：下载成功后，若响应 `content-type` 以 `text/html` 开头，视为下载失败（非真实文件字节）——文件分支降级为 `data=None` 占位项并在 `note` 注明（token scope / 文件权限问题），图片分支记 warning 跳过。MUST NOT 把 HTML 当文件字节返回。

**不做**（明确排除，避免 scope 蔓延，可另案后续）：retry/backoff（hermes 有 3 次重试）；`url_private_download` 优先（保持现有 spec 的 `url_private` 下载语义）；大小上限、文件名安全化、降级占位结构等既有行为均不变。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `im-file-attachment`：在「Slack 适配器下载非图片文件为文件附件项」要求基础上，补充两条下载健壮性约束——下载 client SHALL 跟随 HTTP 重定向（覆盖 Slack 对 PDF 等类型的 302 跨域跳转）；下载返回 `text/html` 内容时 SHALL 视为失败而非文件字节（图片记 warning 跳过、文件降级占位）。既有的大小上限 / 失败降级 / 三路径共用 / 文件名安全化 / 路径注入等要求不变。

## Impact

**owning package**：agent runtime —— `src/fleetent/im_gateway/slack.py`（`_download_attachments`）。全程 agent runtime 侧，**不 import `fleetent.platform.*`**（保持单向依赖）。

**public API surface**：无新增对外 API；`_download_attachments` 签名不变（行为内部收敛）。

**owned tables**：无（零 schema、零迁移）。

**config namespace**：无（无新配置；两条修复无条件生效）。

**cross-module dependencies**：无新增跨模块契约；不触碰 agent↔platform 边界。

**migration / shim plan**：无。

**受影响代码**：`src/fleetent/im_gateway/slack.py`（`_download_attachments` 的 client 构造 + 两分支的 content-type 兜底）；`tests/unit/test_slack_file_download.py`（新增「跟随重定向」「HTML 兜底」用例，复用现有 `_FakeClient` 模式）。
