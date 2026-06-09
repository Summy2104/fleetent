## 1. SDK 升级 + 协议版本改用 LATEST

- [x] 1.1 Write failing test: client.PROTOCOL_VERSION/版本来源 == mcp.types.LATEST_PROTOCOL_VERSION,无手钉常量 — in tests/unit/test_mcp_client_env_url.py(改现有版本断言)
- [x] 1.2 `uv add mcp@latest`;client.py 删手钉 PROTOCOL_VERSION,改 `from mcp.types import LATEST_PROTOCOL_VERSION`;验证 streamablehttp_client/sse_client/stdio_client 签名仍含 url/headers/timeout/auth

## 2. 统一传输:HTTP/SSE 经 SDK 建立持久 ClientSession

- [x] 2.1 Write failing tests for _register_http_server via SDK: mock streamablehttp_client + ClientSession,断言注册后 session 存入 _active_sessions[(scope,id)]、工具按 {id}__{tool} 注册;sse 同理(mock sse_client)— in tests/unit/test_mcp_sdk_transport.py
- [x] 2.2 重写 _register_http_server:按 transport(http/sse)选 SDK client → enter_async_context 进 AsyncExitStack → ClientSession.initialize() → 存 _active_sessions;headers/env: 解析后传 headers=,bearer/api_key 传 headers=/auth=,超时传 timeout/sse_read_timeout;工具经 ClientSession.list_tools 分页列举

## 3. call_tool 合并为单一 session 路径

- [x] 3.1 Write failing tests: _call_via_session 对 http/stdio 都走 _active_sessions[(scope,id)].call_tool();结果经 _normalize_tool_result(base64 不进上下文)— in tests/unit/test_mcp_sdk_transport.py
- [x] 3.2 合并 _call_stdio_tool/_call_http_tool 为 _call_via_session;call_tool 不再按 transport 分流

## 4. 懒重连 + 删后台探活/熔断

- [x] 4.1 Write failing tests: 调用失败(session 抛连接错)→ _reopen_session 重开 → 重试成功;重开仍失败 → 标记不可用 + 返回降级结果;至多重连一次 — in tests/unit/test_mcp_sdk_transport.py
- [x] 4.2 实现 _reopen_session + call_tool 的"失败→重开一次→重试→否则降级";删 _health_monitor_loop/start_health_monitor/_probe_once/_schedule_reconnect/_reconnect_with_backoff/_backoff_delay/熔断计数;HealthState 保留为不可用标记喂 schema 可见性

## 5. 删手写 HTTP 协议代码

- [x] 5.1 删除 _post_jsonrpc / _open_session / _post_notification / _parse_jsonrpc_response / _extract_jsonrpc_from_sse / _is_session_expired / _has_session_invalid_marker / _expire_session / _list_all_tools_http / _base_headers(http 部分,保留 stdio 不需要的部分);清理 _probe_http_tools 改为经临时 SDK session
- [x] 5.2 删除/改写引用上述函数的测试(test_mcp_client.py 的 respx → mock ClientSession;test_mcp_client_compliance.py 的 monkeypatch _post_jsonrpc → mock session)

## 6. 收尾与门禁

- [x] 6.1 实测冒烟：真实 stdio SDK 往返（FastMCP echo 服务）— probe→register→call_tool 正常归一化为文本，且持有 session 跨调用复用；http/sse 共用同一 ClientSession seam（传输选择由 transport 单测覆盖）
- [x] 6.2 Run uv run pytest tests/unit/test_mcp_sdk_transport.py tests/unit/test_mcp_client*.py tests/unit/test_mcp_*.py -q（151 passed across unit+integration MCP）
- [x] 6.3 make test-pr 对照 main 基线,确认无新增失败（2341 passed；4 失败均为既有 path-wiring 基线，与 MCP 无关）
- [x] 6.4 uv run pytest tests/integration -q 对照 main 基线：MCP integration 17 passed；全量 118 个失败/错误均为既有基线（worktree 路径绑定、session DB_PATH 重构遗留、sandbox/docker、install_script 环境）——隔离运行（不含任何 MCP 测试）同样 118 个失败，证明与本次改动无关，无新增失败
- [x] 6.5 uv run mypy src/fleetent/integrations/mcp/client.py
