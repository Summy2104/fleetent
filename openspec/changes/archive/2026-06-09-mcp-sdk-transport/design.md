## Context

`client.py`(~1590 行)中 stdio 已用 SDK(`stdio_client`+`ClientSession`,持久会话存 `_active_sessions[(scope,id)]`,生命周期挂全局 `AsyncExitStack`),HTTP 手写 ~600 行(无状态 per-request POST + 重放 `session_id`)。运维层 ~700 行(健康/熔断/重连/探活/降级/结果规范化/schema 净化/scope)经两个缝调协议层:stdio 走 `session.call_tool()`,http 走 `_post_jsonrpc()`。

SDK 的 `streamablehttp_client`/`sse_client`/`stdio_client` 都产出 `(read, write)` → 同一 `ClientSession` 类型。签名已确认:`streamablehttp_client(url, headers, timeout, sse_read_timeout, terminate_on_close, httpx_client_factory, auth)`、`sse_client(url, headers, timeout, sse_read_timeout, httpx_client_factory, auth, on_session_created)`——`headers`(X-API-Key)、`auth`(Bearer/OAuth)、`timeout`/`sse_read_timeout`(per-server 超时)全覆盖。

## Goals / Non-Goals

**Goals:**
- HTTP/SSE 收敛到 SDK `ClientSession`,与 stdio 统一为一条调用路径
- 删手写 HTTP 协议 ~600 行;协议版本自动跟进
- 长连接降低每次调用延迟(摊销 TCP+TLS,~1 RTT/call)
- 保留运维层应用策略(结果规范化/降级/schema 净化/scope)

**Non-Goals:**
- 不换 OAuth(Change 2 处理);本 change auth 仍手写,注入 SDK transport
- 不加 elicitation/sampling/流续传(SDK 免费带来,本 change 不主动暴露)
- 不动 stdio(已用 SDK)

## Decisions

### D1:三传输统一为长连接 ClientSession(方案 A)
SDK 三种 client 返回同一 `ClientSession` 类型,统一是天然的,无需适配层。`register` 按 `transport` 选 client → `ClientSession` → `initialize()` → 存 `_active_sessions[(scope,id)]`(挂 AsyncExitStack)。`call_tool` 合并为 `_call_via_session`,不分传输。
- **理由**:长连接摊销握手,每次调用 ~1 RTT;现状手写每次新建 httpx client 白付 TLS 握手。stdio 已验证持有模式。
- **代价**:HTTP 引入"连接会死要重连"(见 D2)。

### D2:连接管理瘦身为懒重连
砍后台探活 loop + 熔断机器。`call_tool` 捕获会话/连接错误 → `_reopen_session(server, scope)` 就地重开一次 → 重试一次;仍失败 → 标记 unavailable + 返回降级结果(不崩 loop)。`HealthState` 保留为"上次已知不可用"标记,喂 schema 可见性过滤。
- **理由**:held session 才需重连(stdio 一直需要,HTTP 新增);懒重连足够,省一个常驻任务 + 一大块状态机。代价:空闲很久后首次调用慢一拍(可接受;agent 突发密集用法无感)。

### D3:运维层只通过"持久 session"一个缝与 SDK 交互
结果规范化(`_normalize_tool_result`,base64 不进上下文)、降级 degrade/strict/silent + schema 可见性、schema 净化(definitions→$defs)、headers/env: 解析、`(scope,id)` 键——全部保留,因为它们不碰 wire,只消费 `session.call_tool()`/`list_tools()` 的结果。`(scope,id)` 当前全 None(单 agent),作休眠键零成本保留。

### D4:auth 注入 SDK transport(本 change 范围)
headers/env: 解析后传 `streamablehttp_client(headers=...)`。bearer/api_key 解析结果作为 `headers={"Authorization": ...}` 或 `auth=` 注入。`_bearer_for`/OAuth token 获取保留(Change 2 换 `OAuthClientProvider`)。per-server 超时 → `timeout`/`sse_read_timeout`。

### D5:SDK 升最新 + 协议版本用 LATEST
`uv add mcp@latest`,删手钉 `PROTOCOL_VERSION = "2025-11-25"`,改 `from mcp.types import LATEST_PROTOCOL_VERSION`。

### D6:测试改为 mock ClientSession
HTTP 测试从 `respx`(mock httpx wire)改为注入假 `ClientSession`(断言 `call_tool`/`list_tools` 调用 + 结果规范化)。新增懒重连测试。运维层测试不碰 wire,基本不变。

## Risks / Trade-offs

- **[Risk] SDK 升级改变传输行为** → 锁定 minor 版本;在 task 里验证 transport/auth 签名不变后再升。
- **[Risk] held session 资源占用(N 个常驻连接)** → 5–20 server 量级现代服务可承受;stdio 已持有 N 子进程。懒重连不主动保活,空闲连接由 SDK/OS 回收,首次失败再重开。
- **[Risk] 大改关键子系统 + 删 600 行** → 严格 TDD,逐 task 红绿;make test-pr 对照 main 基线确认无新增失败。
- **[Risk] auth 注入与 SDK transport 交互未验证** → task 里先用 knowledge-bridge/armada(api_key)+ 一个 stdio(jira)实测注册+调用通了再删手写路径。
