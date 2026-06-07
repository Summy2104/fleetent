## Context

`integrations/mcp/client.py` 有 6 处 `httpx.AsyncClient(timeout=...)`：连接/发现/探活/OAuth/关闭用 10.0，工具调用用 30.0。全部写死。agent.yaml 的 `mcp_servers` 经 `McpServerSettings`（`config.py`）解析、`agent_app` 映射为 `McpServerConfig` 注册。

## Goals / Non-Goals

**Goals:**
- per-server `connect_timeout`/`call_timeout`（默认 10/30），消除魔法数字。
- 连接类操作用 connect_timeout，工具调用用 call_timeout。
- 经 agent.yaml `mcp_servers` 声明，operator 无需改代码。

**Non-Goals:**
- Platform DB 列 + admin API 持久化（需 Alembic 迁移）——记为未来单独立项。
- `resetTimeoutOnProgress`——fleetent HTTP 传输是非流式请求/响应（`_post_jsonrpc` 读完整 body），进度重置需把 SSE 读改成逐事件重置 deadline 的流式读，工作量大且宜与未来「Streamable HTTP 流恢复」一并做。
- 不改 stdio 调用超时（SDK 内部管理）。

## Decisions

**D1 两个 per-server 字段。** `McpServerConfig` 加 `connect_timeout: float = 10.0`、`call_timeout: float = 30.0`（普通字段，非 `_`-runtime；它们是配置而非运行态）。

**D2 用点映射。** connect_timeout → `_probe_once`、`_fetch_client_credentials_token`、`_register_http_server`、`_probe_http_tools`（均持有单一 server）；call_timeout → `_call_http_tool`。`_close_http_sessions` 用单个 client 服务**所有** server 的 shutdown DELETE，无单一 server 归属，保持固定 10.0（best-effort 关闭，per-server 意义不大）。

**D3 agent.yaml 直达、不碰 DB 迁移。** `McpServerSettings`（`config.py`）加同名可选字段（默认 10/30；该模型未 `extra="forbid"`，向后兼容）；`agent_app` 的 `McpServerConfig(...)` 映射补 `connect_timeout=s.connect_timeout, call_timeout=s.call_timeout`。这条是 agent 运行时真正读取的配置源，故无需 Alembic 迁移即可让 operator per-server 调超时。DB/admin 持久化（`agent_mcp_server_store` 加列 + `mcp_runtime._row_to_config` + admin API）作为未来机械跟进。

## Risks / Trade-offs

- 字段加在 `McpServerConfig`/`McpServerSettings`，默认值与现状一致 → 零行为变化，纯增量。
- agent_app 映射多两行；由既有 lifespan/agent 测试 + 新字段测试兜底。
- 仅 agent.yaml 路径可设；DB authoring 路径暂用默认（送审记录），需要时补迁移。
