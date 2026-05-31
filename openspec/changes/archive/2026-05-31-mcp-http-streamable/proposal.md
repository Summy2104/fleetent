## Why

`mcp_client.py` 当前的 HTTP 传输（`_register_http_server` / `_call_http_tool`）只是「JSON-RPC over HTTP」的自定义实现：向 `{url}/` 发一个 POST、用固定 `id=1`、只解析 `resp.json()` 的 body。它**不符合官方 MCP Streamable HTTP 规范**——既不接受 `text/event-stream`（SSE）响应，也不识别 `Mcp-Session-Id`，无法接入任何标准 MCP 远程服务（标准服务在 `tools/call` 等请求上会返回 `Content-Type: text/event-stream` 的 SSE 流，而非一次性 JSON body）。docs/capabilities/mcp.md 将「HTTP Streamable 标准支持」列为 v1.0 规划项（`[ ]`），现状仅有 stdio 标准传输与这套非标 HTTP。

这是远程 MCP 集成的地基缺口：客户内网里自托管的标准 MCP 服务（官方 SDK 起的 HTTP server）今天接不进来。本 change 聚焦**传输层标准支持本身**，把 `transport: "http"` 的实现由非标 JSON-RPC 直接**替换重写为标准 Streamable HTTP**，并复用既有的服务注册与 `{server_id}__{tool_name}` 命名空间隔离。经核查仓库无任何 MCP 配置文件（无 `mcp.yaml`）、非标 http 传输无人在用，故直接替换零破坏；同时避免长期维护两条 HTTP 路径，以及「默认 `transport=http` 指向非标实现」的味道。

## What Changes

- **替换 `transport: "http"` 实现为标准 Streamable HTTP**：按 MCP Streamable HTTP 规范实现 `initialize` 握手与 `tools/list` / `tools/call` 的请求-响应；删除原非标 JSON-RPC（固定 `id=1`、仅解析 JSON body）代码。transport 值集合仍为 `{"http", "stdio"}`，不新增值；`"http"`（`McpServerConfig.transport` 的默认值）从此 = **标准 Streamable HTTP**。
  - 请求头 `Accept: application/json, text/event-stream`，使平台同时接受一次性 JSON body 与 SSE 流两种响应形态。
  - 响应 `Content-Type: text/event-stream` 时解析 SSE 事件，提取其中承载 JSON-RPC 响应的 `data:` 行（对应本次请求 `id` 的那条），还原为 JSON-RPC 结果；`application/json` 时按 body 直接解析。
- **会话标识管理（建立侧）**：`initialize` 响应若带 `Mcp-Session-Id` 响应头，则保存到该 server 的运行态；同一 server 后续 `tools/list` / `tools/call` 请求在 header 携带该 `Mcp-Session-Id`。
- **请求 id 唯一化**：每次 JSON-RPC 请求使用单调递增 id（不再固定 `id=1`），SSE 多事件下据 id 匹配本次请求的响应。
- **复用既有注册/命名空间/降级地基**：标准 HTTP 传输仍经 `_register_server` 的 `transport == "http"` 分派（重写其内部实现，不新增分支）；工具仍以 `{server_id}__{tool_name}` 注册进 `tool_registry`；单服务连接失败仍走 `register_all` 的降级（不阻断平台启动）。
- **认证沿用**：继续从 `api_key_env` 读环境变量附加 `Authorization: Bearer`（`auth_type == "api_key"`）。

## Capabilities

### New Capabilities
- `mcp-http-streamable`: MCP Streamable HTTP 标准传输支持——`initialize` 握手、`Accept` 协商 JSON/SSE 双响应、SSE 事件中 JSON-RPC 响应提取、`Mcp-Session-Id` 建立侧管理、单调递增请求 id；工具经既有 `{server_id}__{tool_name}` 命名空间注册进 tool_registry，连接失败沿用降级。

### Modified Capabilities
<!-- stdio 传输行为不变；transport=http 的实现由非标 JSON-RPC 替换为标准 Streamable HTTP。已有 mcp-client 主 spec 无约束 http 非标细节的 requirement，故本 change 以新增能力描述（New Capabilities）承载，非需求级 MODIFIED。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/mcp_client.py`：
    - `McpServerConfig` 增加运行态会话字段承载 `Mcp-Session-Id`（建立后写入；不进可变全局，按 server 实例持有）。
    - **重写 `_register_http_server()`**（发 `initialize` → 保存 session id → `tools/list` → 注册工具）与 **`_call_http_tool()`**（`tools/call`，携带 session id 与递增 id，解析 JSON/SSE 双响应）；删除原非标 JSON-RPC 实现。函数名沿用，不新增 `*_http_streamable_*` 函数。
    - 新增 SSE 响应解析辅助函数（从 `text/event-stream` body 中按 `id` 提取 JSON-RPC 响应对象）。
    - 新增单调递增请求 id 生成（按 server 隔离，可注入/重置以便测试）。
    - `_register_server` / `call_tool` 的 `transport == "http"` 分支保留，指向重写后的标准实现，不新增分支。
- **配置**：`McpServerConfig.transport` 取值仍为 `{"http", "stdio"}`；`"http"` 语义从非标改为标准 Streamable HTTP。
- **测试**：扩展 `tests/test_mcp_client.py`，新增 Streamable HTTP 用例（JSON 响应、SSE 响应、session id 建立与回携、递增 id、连接失败降级、命名空间隔离）；既有非标 http 用例随实现替换为标准实现的回归用例。外部 HTTP 一律用 `respx` mock，**不发真实请求**。
- **不影响**：stdio 传输、命名空间格式、`register_all` 降级语义、API Key 认证既有行为。
- **不引入新依赖**：复用 `httpx`（已用于现有 HTTP 传输）；不引入 AI 框架、ORM、全局可变状态。
