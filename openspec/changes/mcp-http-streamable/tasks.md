## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `_register_server` 分派（mcp_client.py 行 69-73）与 `call_tool`（行 213-219）的 `transport` 判定形态，确认重写 `transport == "http"` 分支的接入点（保留分支、替换实现，不新增分支）
- [ ] 1.2 核实 `McpServerConfig`（行 26-37）字段与 `_server_registry` 持有方式，确定 session_id / 请求 id 计数按 server 隔离的承载位置（不进模块级可变全局）
- [ ] 1.3 核实既有 `tests/test_mcp_client.py` 的 respx mock 模式（行 96-148），确认 SSE 响应可用 `httpx.Response(headers={"content-type": "text/event-stream"}, text=...)` 构造

## 2. SSE 解析纯函数（_extract_jsonrpc_from_sse）

- [ ] 2.1 Write failing tests：`tests/test_mcp_client.py` 喂入 `text/event-stream` 文本，断言 `_extract_jsonrpc_from_sse(body, request_id)` 取出 id 匹配的 JSON-RPC 对象；多行 `data:` 拼接、忽略注释行（`:` 开头）；夹带其他 id 事件时只取本次 id。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `_extract_jsonrpc_from_sse(body: str, request_id: int) -> dict`（行长 100、完整类型注解），看到绿

## 3. 按 server 隔离的请求 id 与会话标识承载

- [ ] 3.1 Write failing tests：`McpServerConfig` 含 `session_id`（默认 None）运行态字段；按 server 取下一个递增请求 id 的辅助（连续调用返回递增值、不同 server 互不影响、可重置）。看到红
- [ ] 3.2 Implement：`McpServerConfig` 增加 `session_id: str | None = None` 与请求 id 计数承载（随 server 实例，不进全局可变状态）+ `_next_request_id(server)` 辅助。看到绿

## 4. initialize 握手 + tools/list 注册（重写 _register_http_server）

- [ ] 4.1 Write failing tests（respx mock，不发真实请求）：`transport: http` 服务注册时先发 `initialize` 再 `tools/list`；`initialize` 响应带 `Mcp-Session-Id` 头 → 保存到 server；`tools/list` 返回的工具以 `{server_id}__{tool_name}` 注册进 `tr._registry`。看到红
- [ ] 4.2 Write failing tests：`initialize` 响应不带 `Mcp-Session-Id` 头时 `server.session_id` 保持 None，注册仍成功。看到红
- [ ] 4.3 Implement：重写 `_register_http_server(server)` 为标准实现——发 `initialize`（`Accept: application/json, text/event-stream`、递增 id、读响应头 `Mcp-Session-Id`）→ 保存 session id → `tools/list`（回携 session id）→ 注册工具；删除原非标 JSON-RPC 代码。看到绿

## 5. tools/call 调用（重写 _call_http_tool）+ JSON/SSE 双响应

- [ ] 5.1 Write failing tests（respx mock）：`tools/call` 响应 `application/json` 时解析 JSON-RPC 结果返回文本；响应 `text/event-stream` 时经 `_extract_jsonrpc_from_sse` 取本次 id 的响应返回文本；请求头携带已保存的 `Mcp-Session-Id` 与递增 id。看到红
- [ ] 5.2 Implement：重写 `_call_http_tool(server_id, tool_name, args)` 为标准实现——构造 `Accept` 头 + Bearer 认证（复用既有 header 构造，沿用 `api_key_env`）+ session id 回携 + 递增 id；按 `Content-Type` 走 JSON 或 SSE 解析；删除原固定 id=1 / 仅 JSON body 解析的非标代码。看到绿

## 6. 分派接入（_register_server / call_tool）

- [ ] 6.1 Write failing tests：`_register_server` 对 `transport == "http"` 路由到重写后的标准注册；`call_tool` 对 `http` server 路由到重写后的标准调用；`transport == "stdio"` 行为不变。看到红
- [ ] 6.2 Implement / 确认：`_register_server` 与 `call_tool` 的 `transport == "http"` 分支指向重写后的标准实现（保留分支、不新增分支）。看到绿

## 7. 连接失败降级（沿用 register_all）

- [ ] 7.1 Write failing tests：两个服务其中一个 `transport: http` 在 `initialize` 阶段不可达（respx 抛 `httpx.ConnectError`）→ `register_all` 不抛异常、失败服务工具不注册、另一服务正常注册。看到红
- [ ] 7.2 Implement / 确认：标准注册异常由既有 `register_all` 的 `try/except` 捕获降级（如未覆盖则补齐路径），看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（按项目要求带 `ANTHROPIC_API_KEY`）通过，stdio 传输用例无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误模式
- [ ] 8.3 加回归守卫：`transport == "http"` 现为标准实现的回归用例（JSON/SSE 双响应、session 回携、递增 id）；stdio 传输路径用例保持原行为不变
