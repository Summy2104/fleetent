## Why

fleetent 的 MCP 客户端是混合实现:stdio 已用官方 `mcp` SDK(`stdio_client` + `ClientSession`),但 HTTP 传输是手写的 ~600 行(JSON-RPC POST、SSE 解析、会话管理、协议版本)。手写层是在重造 SDK 已提供的 `streamablehttp_client`,且更旧、有 bug(URL 尾斜杠、isinstance 误判)、缺特性(无 SSE legacy 传输、协议版本手钉、无流续传/elicitation/sampling),并且与 stdio 形成两套代码路径。

`mcp` SDK 早已是声明依赖(`mcp>=1.0.0`,已装 1.27.1),stdio 路径已在用——这不是"引入新依赖",而是把 HTTP 也收敛到已用的 SDK。同时手写 HTTP 每次工具调用新建 httpx client、白付一次 TLS 握手;改为 SDK 长连接后每次调用摊销到 ~1 RTT。

这是"完全迁移到官方 SDK"两个顺序 change 的**第一个(传输层)**;第二个 `mcp-sdk-oauth`(OAuth → SDK `OAuthClientProvider`)随后单独做。

## What Changes

- **统一传输**:HTTP(`streamablehttp_client`)/ SSE(`sse_client`)与 stdio 一样产出 `(read, write)` → 喂同一 `ClientSession` → 持久存 `_active_sessions[(scope, id)]` 挂 `AsyncExitStack`。`call_tool` 塌缩为一条路径,不再按 transport 分流。
- **删 ~600 行手写 HTTP 协议**:`_post_jsonrpc` / `_open_session` / `_post_notification` / `_parse_jsonrpc_response` / `_extract_jsonrpc_from_sse` / `_base_headers`(http 部分)/ `_is_session_expired` / `_has_session_invalid_marker` / `_expire_session` / `_list_all_tools_http`;删手钉 `PROTOCOL_VERSION`。
- **连接管理瘦身为懒重连**:砍后台探活 loop + 指数退避熔断(`_health_monitor_loop`/`start_health_monitor`/`_probe_once`/`_schedule_reconnect`/`_reconnect_with_backoff`);保留"`call_tool` 失败 → 就地 `_reopen_session` 重开一次 → 重试;仍失败返回降级结果不崩 loop"。
- **SDK 升最新版** + 协议版本改用 `mcp.types.LATEST_PROTOCOL_VERSION`。
- **保留运维层应用策略**(SDK 给不了):结果规范化、降级模式 + schema 可见性、schema 净化、headers/env: 解析(传 SDK transport `headers=`)、`(scope,id)` 键。
- **auth 本 change 仍手写**:bearer/api_key 注入 SDK transport 的 `headers=`/`auth=`(OAuth → SDK 留给 Change 2)。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `mcp-http-streamable`: 手写 HTTP 协议 → 官方 SDK `streamablehttp_client`/`sse_client` 持有的 `ClientSession`
- `mcp-session-continuity`: 手写会话过期检测重建 → 懒重连(调用失败时就地重开一次)
- `mcp-health-reconnect`: 后台探活 + 指数退避熔断 → 懒重连 + "上次已知不可用"标记
- `mcp-client-compliance`: 手钉协议版本 → `mcp.types.LATEST_PROTOCOL_VERSION`

## Impact

- `src/fleetent/integrations/mcp/client.py`:删手写 HTTP 协议、统一会话路径、懒重连、协议版本
- `pyproject.toml`:`mcp` 升最新版
- `tests/`:HTTP 测试从 `respx`(mock httpx)改为 mock `ClientSession`;新增懒重连测试
- 无新依赖(`mcp` 已依赖)
- stdio 行为不变(已用 SDK);HTTP/SSE 用户配置不变(transport/url/headers/auth 字段不变)
- 不变 spec:mcp-degradation、mcp-result-handling、mcp-dynamic-tools、mcp-stdio-isolation、mcp-resources-prompts、mcp-per-server-timeout、mcp-oauth2-auth
