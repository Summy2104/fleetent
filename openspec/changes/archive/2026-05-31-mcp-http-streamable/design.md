## Context

`mcp_client.py` 现有两种传输：`stdio`（官方 MCP SDK，标准）与 `http`（自定义 JSON-RPC over HTTP，非标）。非标 HTTP 路径（`_register_http_server` 行 104、`_call_http_tool` 行 178）固定向 `{url}/` 发一个 POST、固定 `id=1`、只 `resp.json()` 解析 body，不接受 SSE、不识别 `Mcp-Session-Id`。官方 MCP **Streamable HTTP** 规范要求客户端在请求头声明 `Accept: application/json, text/event-stream`，服务端可对 `tools/call` 等返回 SSE 流（`Content-Type: text/event-stream`），其中以 `data:` 行承载 JSON-RPC 响应；`initialize` 响应可通过 `Mcp-Session-Id` 头分配会话标识，后续请求须回携。

服务注册在 `register_all` → `_register_server`（按 `transport` 分派）；工具统一以 `{server_id}__{tool_name}` 注册进 `tool_registry._registry`；单服务连接失败由 `register_all` 捕获并降级（warning，不阻断启动）。本 change 复用这套地基，把 `transport == "http"` 的实现替换为标准传输。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；**禁止全局可变状态**（递增 id 与 session id 须可注入/重置、按 server 隔离，便于测试）；外部 HTTP 必须用 respx/mock，不发真实请求；MCP 工具名用双下划线 `{server_id}__{tool_name}`；行长 100；mypy strict；测试落在 `tests/test_mcp_client.py`。

## Goals / Non-Goals

**Goals:**
- 按 MCP Streamable HTTP 规范实现传输：`initialize` 握手、`Accept` 协商、JSON 与 SSE 双响应解析、`tools/list` / `tools/call`。
- `initialize` 时保存服务端分配的 `Mcp-Session-Id`，后续同 server 请求回携。
- 每次 JSON-RPC 请求使用单调递增 id，SSE 多事件下据 id 匹配本次响应。
- 标准传输经既有 `_register_server` 分派、复用 `{server_id}__{tool_name}` 命名空间与 `register_all` 降级。
- 把 `transport == "http"` 的实现由非标替换为标准，不新增 transport 值。

**Non-Goals:**
- 不实现**会话连续性恢复**：服务端 404（会话过期）后的自动重新 `initialize` 与透明重试属后续 change。
- 不实现**健康检查与重连**（探活、指数退避、永久不可用标记）——后续 change。
- 不实现**完整运行时降级策略**（degrade / strict / silent 模式切换）——本次仅保留 `register_all` 既有的启动失败降级。
- 不实现 **OAuth2 / Token 自动刷新**——继续沿用 `api_key_env` 的 Bearer 认证。
- 不实现**断线流恢复**（`Last-Event-ID` 续传）——本次只在单次请求内消费 SSE 直至取得本次 JSON-RPC 响应。
- 不改 stdio 传输、命名空间格式、API Key 认证既有行为。

## Decisions

### D1：替换非标 http 实现为标准 Streamable HTTP（不新增 transport 值）
把 `transport == "http"` 的实现从自定义 JSON-RPC（`_register_http_server` / `_call_http_tool`，固定 id=1、仅解析 JSON body）整体重写为标准 Streamable HTTP；transport 值集合仍为 `{"http", "stdio"}`，`"http"`（默认值）从此即标准实现。`_register_server` 与 `call_tool` 的 `transport == "http"` 分支保留，指向重写后的实现。
**为何**：经核查仓库无任何 MCP 配置文件（无 `mcp.yaml`）、非标 http 传输无人在用，直接替换零破坏；且避免长期维护两条 HTTP 路径，以及「默认 `transport=http` 指向非标实现」的味道。spec 的命名空间与降级要求对 http 路径不变，故复用同一注册/降级地基。
**Alternatives**：①新增 transport 值 `"http_streamable"` 与既有 `"http"` 并存——被否，无人在用却长期维护两条 HTTP 路径，且默认 `"http"` 仍指非标，味道不正；②单一 `"http"` 下原地探测响应类型在两套语义间兼容——被否，`initialize` 与 session 语义是标准独有，探测会让分派逻辑复杂且难单测。

### D2：`Accept` 协商 + JSON/SSE 双响应解析
所有标准请求头带 `Accept: application/json, text/event-stream`。读响应 `Content-Type`：
- `application/json`：直接 `resp.json()` 取 JSON-RPC 响应。
- `text/event-stream`：逐行解析 SSE，收集 `data:` 行拼成 JSON，挑出 `id` 等于本次请求 id 的 JSON-RPC 响应对象。
解析逻辑抽成纯函数 `_extract_jsonrpc_from_sse(body: str, request_id: int) -> dict`，便于单测（不发请求，直接喂 SSE 文本）。
**为何**：规范允许服务端按请求二选一返回；双解析使平台对两种形态都正确取值。纯函数化是为可单测、避免在网络层耦合解析。
**Alternatives**：①只支持 SSE——被否，规范允许 JSON 形态，部分服务对简单请求返回 JSON；②引入第三方 SSE 库——被否，违背「无新依赖」，单次请求内的逐行解析足够简单。

### D3：`Mcp-Session-Id` 建立侧管理（不进全局可变状态）
`initialize` 响应头若含 `Mcp-Session-Id`，写入该 server 的运行态（在 `McpServerConfig` 增加 `session_id: str | None` 运行态字段，或与 `_server_registry[server.id]` 一并持有），后续 `tools/list` / `tools/call` 在 header 携带 `Mcp-Session-Id: <id>`。session id 随 server 实例持有，不放模块级可变全局；测试可直接构造带/不带 session id 的 server 验证回携。
**为何**：规范要求会话内请求回携 session id；按 server 持有满足「禁止全局可变状态」与测试隔离。本次只做**建立 + 回携**，过期重建（404 → 重新 initialize）属 Non-Goals。
**Alternatives**：模块级 `dict[str, str]` 存 session id——被否，是全局可变状态，违反 CLAUDE.md，且测试需 monkeypatch 清理。

### D4：单调递增请求 id（按 server 隔离，可注入/重置）
不再固定 `id=1`。每个 server 维护一个递增计数器生成请求 id；SSE 含多事件时据 id 取本次响应。计数器随 server 运行态持有（非全局），测试可重置。
**为何**：SSE 流可能夹带服务端通知/其他事件，固定 id 无法区分本次响应；递增 id 是规范实践。按 server 隔离避免全局可变状态。
**Alternatives**：固定 id=1 + 取首个带 `result` 的事件——被否，无法在多事件下保证取到本次响应，语义脆弱。

### D5：`initialize` 握手纳入注册流程
标准传输注册顺序：`initialize`（声明 protocolVersion + clientInfo，读取 session id）→ `tools/list`（注册工具）。
**为何**：规范要求会话以 `initialize` 开端，session id 在此分配；不握手则后续请求缺 session 上下文。
**Alternatives**：跳过 `initialize` 直接 `tools/list`——被否，不符合规范，且取不到 session id。

### D6：复用既有命名空间与降级，不新增基础设施
工具仍走 `_make_tool_name(server.id, tool_name)` 注册进 `tr._registry`；连接/握手失败由 `register_all` 的 `try/except` 捕获并 warning 降级。标准传输不引入新模块、不引入新依赖（复用 `httpx`）。
**为何**：spec 要求命名空间与降级对 http 传输一致；复用地基改动最小、风险最低。

## Risks / Trade-offs

- [替换后若未来需非标兼容] → 已核查仓库无任何 MCP 配置文件（无 `mcp.yaml`）、非标 http 传输无人在用，零破坏；未来若确需非标兼容，再单列 change 引入，不在本次背负。
- [SSE 解析对非常规分帧（多行 data、注释行、event 字段）不鲁棒] → `_extract_jsonrpc_from_sse` 按规范处理多行 `data:` 拼接、忽略注释（`:` 开头）与非 data 字段；用多形态 SSE 文本单测覆盖。
- [递增 id 在 SSE 多事件下仍取错响应] → 严格按 `id == request_id` 过滤，仅接受含 `result` 或 `error` 且 id 匹配的对象；单测构造夹带额外事件的 SSE 验证。
- [服务端返回 SSE 但不含本次 id 的响应（仅通知）] → 本次实现只在单请求内消费至取得本次响应；取不到则视为失败（抛错经 `register_all` 降级 / 工具调用返回错误），不静默挂起——超时沿用 httpx timeout。

## Open Questions

- `initialize` 上报的 `protocolVersion` 取值——实现首步对照所接入的标准 MCP server 版本确定；不影响传输框架结构。
- 是否需要在 `tools/call` 后向服务端发送 `notifications/initialized`（部分服务要求）——实现时按目标 server 行为确认，必要时在 `initialize` 后补一条通知；属实现细节，不改 spec 行为。
