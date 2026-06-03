## Why

MCP1（mcp-http-streamable，已合入）把 `transport: "http"` 重写为标准 Streamable HTTP：`initialize` 握手时若服务端经 `Mcp-Session-Id` 响应头分配会话标识，则保存到 `McpServerConfig.session_id`，后续 `tools/list` / `tools/call` 在请求头回携。但 MCP1 只做了会话标识的**建立 + 回携**（见其 Non-Goals「不实现会话连续性恢复」）：

- **会话过期无人处理**：标准 MCP server 可在会话失效后对携带旧 `Mcp-Session-Id` 的请求返回 HTTP 404（或 4xx 会话错误）。当前 `_post_jsonrpc` 直接 `resp.raise_for_status()` 抛出，工具调用失败，调用方无感知地拿到一个错误——而规范预期客户端应重新 `initialize` 取新会话标识后透明重试（docs/capabilities/mcp.md 场景 4）。
- **会话生命周期无显式收口**：`session_id` 作为裸字段散落在握手代码里，没有「开启 / 复用 / 关闭」的统一入口；`close()` 仅清理 stdio 的 `_active_sessions`，HTTP server 的 `session_id` 不被显式失效，重启注册时复用旧 server 实例会带着陈旧会话标识。
- **规范要求服务端在会话结束时收到 `DELETE`**：标准 Streamable HTTP 允许（部分要求）客户端在不再使用会话时对会话端点发 HTTP `DELETE` 主动关闭，避免服务端会话泄漏；当前无此动作。

这是 MCP2（会话管理），直接建立在 MCP1 之上：把 MCP1 暴露的会话标识从「一个被动保存的字段」提升为「有显式生命周期的会话句柄」——开启、跟踪、过期重建、关闭。本 change 聚焦**会话连续性本身**，不碰健康探活/重连（MCP3）与认证（MCP5）。

## What Changes

- **会话过期透明重建**：`tools/list` / `tools/call` 请求收到服务端会话失效响应（HTTP 404，或 4xx 且响应体/头部指示会话无效）时，平台清空该 server 的 `session_id`，重新发起 `initialize` 取得新会话标识，并对原请求重试**一次**；重建成功后调用方无感知拿到正常结果，重建失败则按既有错误路径上抛（交由降级/上层处理）。
- **会话生命周期显式收口**：引入会话句柄管理的统一入口——`open`（initialize 取得并保存 session id）、`reuse`（后续请求回携）、`expire`（清空本地 session id，准备重建）、`close`（结束会话）。会话状态仍按 server 实例隔离持有（沿用 MCP1 的 `McpServerConfig.session_id`），不进模块级可变全局。
- **会话主动关闭（DELETE）**：`close()`（server 关停）时，对持有 `session_id` 的 HTTP server 向会话端点发送 `DELETE` 通知服务端释放会话（best-effort，失败仅记日志不阻断关停）；关闭后清空本地 `session_id`。
- **重建次数受限**：单次工具调用 / 列举的会话重建至多触发一次，避免「过期 → 重建 → 再过期」的无限循环；重试仍失败则按错误上抛。
- **复用 MCP1 地基**：会话标识仍源自 `initialize` 的 `Mcp-Session-Id`、仍按 server 回携；递增请求 id、SSE/JSON 双解析、`{server_id}__{tool_name}` 命名空间、`register_all` 降级均不变。

## Capabilities

### New Capabilities
- `mcp-session-continuity`: MCP Streamable HTTP 会话连续性管理——会话过期（HTTP 404 / 会话失效响应）时透明重新 `initialize` 并对原请求重试一次；会话生命周期显式收口（开启 / 复用 / 过期重建 / 关闭）；server 关停时对活跃会话发 `DELETE` 主动释放；会话状态按 server 隔离持有，不进全局可变状态。

### Modified Capabilities
<!-- 不修改既有 spec 的需求级行为。mcp-http-streamable 主 spec 已声明「会话标识建立 + 回携」，本 change 在其上新增「过期重建 + 关闭」连续性能力，以 New Capabilities 承载；transport=http 的正常注册/调用可观察行为在会话有效时不变。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/mcp_client.py`：
    - 引入会话生命周期辅助函数（`open` / `reuse` / `expire` / `close` 语义），把 MCP1 散在握手中的 `session_id` 保存/回携收口为显式入口；状态仍持于 `McpServerConfig.session_id`（不进全局）。
    - `_post_jsonrpc`（或其调用方 `_call_http_tool` / 注册时的 `tools/list`）增加会话失效识别：HTTP 404 或 4xx 会话错误 → `expire` → 重新 `initialize`（reuse 新 session id）→ 重试一次。
    - `close()` 对每个持有 `session_id` 的 HTTP server 发 `DELETE` 释放会话（best-effort），并清空 `session_id`。
  - 不新增模块。
- **配置**：无新增 Settings / `config/mcp.yaml` 字段（会话重建为协议层行为，不需部署级开关）。
- **测试**：扩展 `tests/test_mcp_client.py`，新增会话连续性用例（404 触发重建并透明重试成功、重建后仍失败上抛、重建至多一次、`close()` 对活跃会话发 `DELETE`、无 session id 时不发 `DELETE`）。外部 HTTP 一律 `respx` mock，**不发真实请求**。
- **不影响**：stdio 传输、命名空间格式、`register_all` 降级语义、API Key 认证、MCP1 在会话有效时的正常注册/调用行为。
- **不引入新依赖**：复用 `httpx`（MCP1 已用）；不引入 AI 框架、ORM、全局可变状态。
