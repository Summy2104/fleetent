## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 MCP1 现状：`_register_http_server`（mcp_client.py 行 220-257）如何发 `initialize` 并从响应头取 `Mcp-Session-Id` 写入 `server.session_id`；`_base_headers`（行 166-175）如何回携；`_post_jsonrpc`（行 189-203）在何处 `raise_for_status`，确认重建逻辑的插入点
- [ ] 1.2 核实标准 MCP server 会话失效响应特征：HTTP 404 为主锚点；确认 400/401/403 等 4xx 是否会被误判，定 D1 的会话失效识别口径（401/403 不触发重建）
- [ ] 1.3 核实 `close()`（行 108-114）现状仅清 stdio `_active_sessions`，确认对 HTTP server 发 `DELETE` 的插入点与 `_server_registry` 可遍历性
- [ ] 1.4 核实会话端点：`DELETE` 与 `tools/call` 是否同 `{url}/` 端点、携 `Mcp-Session-Id` 头（对照目标 server 与规范）

## 2. 会话生命周期辅助函数（mcp_client.py）

- [ ] 2.1 Write failing tests：会话生命周期入口的语义——`open`（initialize 后 `server.session_id` 被写入 mock 返回的 id）、`reuse`（`_base_headers` 在有 session id 时含 `Mcp-Session-Id`，无则不含）、`expire`（调用后 `server.session_id` 为 None）。respx mock initialize 响应头。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement 会话生命周期辅助函数（把 MCP1 散在握手中的 session id 保存/回携/清空收口为显式入口；状态仍持于 `McpServerConfig.session_id`，不进全局），看到绿

## 3. 会话过期透明重建（tools/list 与 tools/call）

- [ ] 3.1 Write failing tests：`tools/call` 首次请求收到 HTTP 404 → 平台 `expire` 旧 session id、重新 `initialize` 取新 id、用新 id 重试一次并返回正常结果；调用方拿到的结果与无过期时一致（透明）。respx mock：第一次 404、initialize 返回新 `Mcp-Session-Id`、重试返回正常 JSON-RPC。看到红
- [ ] 3.2 Implement：在 `_post_jsonrpc` 识别会话失效（D1 口径），**且检测必须在 `resp.raise_for_status()`（行 199）之前进行**（D1a：要么前移读 `resp.status_code` 再决定是否 raise，要么捕获 `httpx.HTTPStatusError` 按 `e.response.status_code` 判定）→ `expire` → 重新 `initialize` → 重发原请求，至多一次（`_allow_session_retry` 布尔，重试时置 False），看到绿
- [ ] 3.3 Write failing tests：`tools/list`（注册期）遇 404 同样触发会话重建并完成注册（工具仍以 `{server_id}__{tool_name}` 注册）。看到红
- [ ] 3.4 Implement 使注册期重建通过，看到绿
- [ ] 3.5 Write failing tests 重建至多一次：连续两次 404 时，第二次不再重建、按错误上抛（不无限循环）；覆盖 `tools/call`（调用期）与 `tools/list`（注册期）两路径，验证守卫作用于二者共享的 `_post_jsonrpc`、与路径无关。看到红
- [ ] 3.6 Implement 使「至多一次」守卫通过（守卫落在共享请求层，调用期/注册期对称），看到绿
- [ ] 3.7 Write failing test 认证错误不触发重建：401/403 响应按错误上抛、`server.session_id` 不被清空、不发起重新 initialize。看到红
- [ ] 3.8 Implement 使认证错误不触发会话重建（D1：401/403 不判会话过期），看到绿

## 4. close() 主动释放会话（DELETE）

- [ ] 4.1 Write failing tests：`close()` 对持有 `session_id` 的 HTTP server 向会话端点发 `DELETE`（带 `Mcp-Session-Id` 头），随后 `session_id` 被清空；无 `session_id` 的 server 不发 `DELETE`；`DELETE` 失败仅记日志、不抛、不阻断关停。respx mock DELETE。看到红
- [ ] 4.2 Implement：`close()` 遍历 `_server_registry` 中活跃 HTTP 会话发 `DELETE`（best-effort，失败 `logger.debug`），清空 `session_id`，看到绿

## 5. 收尾

- [ ] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 5.3 `uv run mypy src` 无新增错误
