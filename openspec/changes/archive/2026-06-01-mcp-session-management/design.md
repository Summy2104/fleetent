## Context

MCP1（mcp-http-streamable，已合入）把 `transport: "http"` 重写为标准 Streamable HTTP：`_register_http_server`（mcp_client.py 行 220）发 `initialize`，从响应头读 `Mcp-Session-Id` 写入 `server.session_id`（行 240-242）；`_base_headers`（行 166）在有 `session_id` 时回携 `Mcp-Session-Id` 头；`_post_jsonrpc`（行 189）发请求后 `resp.raise_for_status()`（行 199）。`McpServerConfig.session_id: str | None`（行 43）按 server 实例持有，非模块级全局。MCP1 明确把「会话连续性恢复（404 → 重新 initialize）」列为 Non-Goals。

docs/capabilities/mcp.md 场景 4 定义了目标行为：「与远程 HTTP 服务的会话已过期 → 下次工具调用服务端返回 404 → 平台自动重新 initialize 获取新 Session ID，工具调用重试成功，调用方无感知」。本 change 把这条路径接通。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；**禁止全局可变状态**（会话状态须按 server 隔离、可注入/重置以便测试）；外部 HTTP 必须用 respx/mock，不发真实请求；MCP 工具名用双下划线 `{server_id}__{tool_name}`；行长 100；mypy strict；TDD Hard Gate；测试落在 `tests/test_mcp_client.py`。

## Goals / Non-Goals

**Goals:**
- 会话过期（HTTP 404 / 4xx 会话失效）时，清空本地 session id、重新 `initialize` 取新标识、对原请求透明重试一次。
- 把 MCP1 散在握手中的 session id 保存/回携，收口为显式的会话生命周期入口（open / reuse / expire / close）。
- `close()`（server 关停）对持有 session id 的 HTTP server 发 `DELETE` 释放会话（best-effort），清空本地 session id。
- 会话重建至多一次，避免无限循环。
- 会话状态仍按 server 实例隔离持有，不进模块级可变全局。

**Non-Goals:**
- 不实现**健康探活与重连**（周期 ping、指数退避、永久不可用标记）——MCP3。
- 不实现 **OAuth2 / Token 刷新**——MCP5；本 change 沿用 `api_key_env` Bearer。
- 不实现**断线流恢复**（`Last-Event-ID` 续传中断的 SSE 流）——本次重建是「整段重新 initialize + 重试整条请求」，非流级续传。
- 不改 stdio 传输、命名空间格式、API Key 认证、`register_all` 启动降级语义。
- 不消费 AR5 的 `mcp_disconnect` 分类码（那是 MCP3 的连接级断连恢复；本 change 处理的是会话级过期，属同一请求内的协议重建）。

## Decisions

### D1：会话失效识别口径——HTTP 404 优先，4xx 会话错误兜底
`_post_jsonrpc` 发请求后，若响应状态码为 404（规范中服务端对失效 `Mcp-Session-Id` 的典型响应），判定为会话过期；对 400/401/403 等 4xx，仅当响应体/头部含明确会话失效标识（如 JSON-RPC error 指示 session 无效）时才判会话过期，否则按原错误路径处理（`raise_for_status` / RuntimeError）。
**为何**：docs/capabilities/mcp.md 场景 4 以 404 为锚点；过宽地把所有 4xx 当会话过期会与 MCP5 的认证失败（401/403）语义冲突——认证失败不该触发会话重建而该上抛（AR5 `auth_failed` 全 False，不重试）。以 404 为主、其余 4xx 需显式会话标识，避免误判。
**Alternatives**：①任何非 2xx 都重建——被否，401/403 认证错误会被错误地无限/一次重建，掩盖真正的认证问题；②仅 404——被否，部分服务用 400 + 会话错误体，留兜底但要求显式标识。

#### D1a：会话失效**必须在 `raise_for_status()` 之前**检测（插入点前移/守卫）
MCP1 现状（mcp_client.py 行 199）是 `_post_jsonrpc` 一拿到 `resp` 就先 `resp.raise_for_status()`——404/4xx 在能进入 D1 的会话判定分支前，已被抛成 `httpx.HTTPStatusError`。因此本 change 的会话失效检测 **MUST NOT** 写成「`raise_for_status()` 之后再看状态码」（那永远到不了）。实现 **必须**二选一：
- **(a) 前移检测（首选）**：在 `raise_for_status()` 调用之前先读 `resp.status_code`——命中 D1 会话失效口径（404 / 4xx + 显式会话标识）则进入 `expire` → 重新 `initialize` → 重试一次路径；不命中再 `raise_for_status()` 走原错误路径。
- **(b) 捕获再判定**：把 `raise_for_status()` 包在 `try`，`except httpx.HTTPStatusError as e` 中按 `e.response.status_code` 判 D1 口径——命中则重建重发，不命中则 `raise`。

不得保留「先 `raise_for_status()`、后看状态码」的死分支。
**为何**：评审指出 D1 的描述（「响应状态码为 404 → 判定为会话过期」）读起来像内联检查，但没点明插入点要绕开行 199 的 `raise_for_status()`；不写清楚实现者会到编码中途才发现需重构该函数。两种写法均可，关键是会话判定发生在 raise 之前或捕获 raise 之后，二者择一并在实现首步定夺。
**Alternatives**：保留 `raise_for_status()` 在前、其后再分支——被否，404 已成异常，分支不可达。

### D2：透明重试至多一次（重建发生在请求层，不在工具语义层）
检测到会话过期 → `expire`（清空 `server.session_id`）→ 重新 `initialize`（写入新 session id，触发 `notifications/initialized`）→ 用新 session id 重发原 `method`（同一 `tools/call` / `tools/list` 的 params，分配新递增请求 id）。重试以一个布尔标志（`_allow_session_retry` 入参，默认 True）控制，重试时置 False，确保**至多一次**；若重试仍 404/失败则按错误上抛。
**为何**：会话过期是瞬态、单次重建即恢复；限定一次避免「过期→重建→再过期」无限循环。重建放在 `_post_jsonrpc` 层对 `tools/list` 与 `tools/call` 都生效，调用方无感知（符合场景 4「调用方无感知」）。
**Alternatives**：①重建逻辑塞进 `_call_http_tool`——被否，`tools/list`（注册期）也可能遇会话过期，放 `_post_jsonrpc` 一处覆盖两者；②无限重试直到成功——被否，过期成因若非瞬态（如服务端拒绝建会话）会死循环。

### D3：会话生命周期显式收口（open / reuse / expire / close 语义），状态仍持于 McpServerConfig
不引入新数据类或模块级会话表，而是把 MCP1 已有的 `server.session_id` 字段的操作收口为语义清晰的辅助函数：
- `open`：发 `initialize`、从响应头取 `Mcp-Session-Id` 写入 `server.session_id`（即 MCP1 已有逻辑，抽出复用以便重建调用）。
- `reuse`：`_base_headers` 在有 session id 时回携（MCP1 已有）。
- `expire`：把 `server.session_id` 置 None（重建前调用）。
- `close`：对持有 session id 的 server 发 `DELETE` 后置 None（见 D4）。
**为何**：CLAUDE.md 禁止全局可变状态；MCP1 已把 session id 放 `McpServerConfig` 实例（非全局），本 change 沿用——只是给「写 / 清 / 用」加语义入口，便于重建路径复用 `open` 而非复制握手代码。引入新会话表反而制造另一处需 monkeypatch 清理的状态。
**Alternatives**：①新增 `McpSession` 数据类或模块级 `dict[str, McpSession]`——被否，重复 MCP1 已落在 server 实例上的状态，且 dict 是全局可变状态违反 CLAUDE.md；②每次请求都重新 initialize（无状态）——被否，违背会话「连续性」本意，且每调用一次工具多一次握手开销。

### D4：close() 对活跃会话发 DELETE（best-effort）
`close()` 现仅 `_exit_stack.__aexit__` + 清 `_active_sessions`（stdio）。本 change 在其中遍历 `_server_registry` 中 `transport == "http"` 且 `session_id` 非空的 server，对会话端点发 HTTP `DELETE`（带 `Mcp-Session-Id` 头）通知服务端释放，随后置空 `session_id`。`DELETE` 失败（网络/服务端不支持）仅 `logger.debug`，不抛、不阻断关停（与 MCP1 `_post_notification` 的 best-effort 风格一致，不吞——记日志）。
**为何**：规范允许客户端主动 `DELETE` 会话，避免服务端会话泄漏；关停是 best-effort 场景，服务端可能已不可达，失败不该阻断进程退出。
**Alternatives**：①不发 DELETE，靠服务端超时回收——被否，规范鼓励主动释放，长生命周期服务端会话泄漏；②DELETE 失败也抛——被否，关停路径抛异常会掩盖其他清理，best-effort 更稳。

### D5：与 AR5 / MCP3 的边界
本 change 处理的是**会话级过期**（同一 TCP 连接仍在，服务端只是判定 `Mcp-Session-Id` 失效）——这是协议层重建，发生在单次请求内，调用方无感知，**不**经 AR5 的 `classify()`，**不**返回 `mcp_disconnect`。MCP3 处理的是**连接级断连**（服务不可达、子进程死、连续失败）——那才映射到 AR5 `mcp_disconnect`（should_retry=True）并触发连接重连/降级。两者职责正交：会话重建失败若进一步表现为连接不可达，由 MCP3 的连接级路径接管。
**为何**：避免 MCP2 与 MCP3 都去碰「重连」语义而冲突；明确「会话过期 = MCP2 协议重建」「连接断开 = MCP3 + AR5」的分层。

## Risks / Trade-offs

- [会话失效识别误判（把认证 401/403 当会话过期）] → D1 以 404 为主、其余 4xx 需显式会话失效标识；401/403 默认不触发重建而上抛，与 MCP5 认证失败语义不冲突。加用例：401 不触发会话重建。
- [重建后立即再过期导致循环] → D2 以 `_allow_session_retry` 布尔限定至多一次；重试仍失败按错误上抛。加用例：连续两次 404 时第二次直接上抛、不再重建。
- [并发请求对同一 server 同时重建（同时清空/重写 session_id）] → 本 change 不引入并发会话锁。`server.session_id` 是无锁的可变字段，并发重建是对它的 read-modify-write，**可能交错**（两请求都判过期、都重发 initialize、后写覆盖先写）。本 change 不保证此处严格无交错，仅声明最坏后果有界：**最多多触发一次重建 / 一次 `initialize`**，每个请求最终都用某个有效的新 session id 完成或按错误上抛——不会因交错产生无限重建或永久错误状态。是否需要 per-server 锁（仿 session_mgr 的 per-session asyncio.Lock）以消除交错，列为 Open Question；高并发实测出现问题再加。
- [close() 的 DELETE 在服务端不支持时报错刷日志] → 失败仅 `logger.debug`，不影响关停；不视为错误。

## Open Questions

- 会话失效的精确响应特征：除 HTTP 404 外，目标自托管 MCP server 是否用 400 + 特定 JSON-RPC error code 表达会话失效——实现首步对照所接入标准 MCP server 行为核实 D1 的 4xx 兜底判据。
- `DELETE` 的会话端点路径：是否即 `{url}/`（同 POST 端点）携 `Mcp-Session-Id` 头——按规范应同端点，实现时对照目标 server 确认；不改 spec 行为。
- 同一 server 高并发下的会话重建是否需要 per-server 锁（仿 session_mgr 的 per-session asyncio.Lock）以消除 `session_id` read-modify-write 交错——本次接受无锁，仅保证「最坏多一次重建 / 一次 initialize」的有界后果（非严格幂等）；高并发实测出现问题再加锁。
