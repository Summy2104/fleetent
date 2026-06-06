## Why

MCP 客户端的所有 HTTP 超时都是写死的魔法数字（连接/发现 10s、工具调用 30s）。企业内网的 MCP 服务快慢差异大：慢服务（大数据查询、跨系统编排）会在 30s 被硬切，快服务又想要更紧的超时以快速失败。超时应当 per-server 可配，而非全局写死。

## What Changes

- `McpServerConfig` 新增 `connect_timeout`（默认 10.0）与 `call_timeout`（默认 30.0）两个 per-server 字段。
- MCP 客户端的 HTTP 操作改用 per-server 超时：连接/发现/探活/OAuth token 取用 `connect_timeout`；工具调用用 `call_timeout`。（shutdown 时一次性释放所有会话的 best-effort DELETE 仍用固定超时——它用单个 client 服务全部服务，无单一 server 归属。）
- agent.yaml 的 `mcp_servers` 条目可声明 `connect_timeout`/`call_timeout`（`McpServerSettings` 加可选字段，缺省用默认），经 `agent_app` 透传到运行时——operator 无需改代码即可 per-server 调超时。

非破坏性：未声明超时的服务沿用 10s/30s 默认，行为不变。

## Capabilities

### New Capabilities
- `mcp-per-server-timeout`: 定义 MCP 客户端 HTTP 操作的 per-server 连接/调用超时，及其经 agent 配置的声明方式。

### Modified Capabilities
<!-- 无：现有 spec 未对超时可配性作出要求，为纯新增能力。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`（`McpServerConfig` 加字段；`_probe_once`/`_fetch_client_credentials_token`/`_register_http_server`/`_probe_http_tools` 用 `connect_timeout`，`_call_http_tool` 用 `call_timeout`）；`src/fleetent/config.py`（`McpServerSettings` 加 `connect_timeout`/`call_timeout`）；`src/fleetent/runtime/agent_app.py`（透传两字段）。
- 行为：慢/快 MCP 服务可分别调超时；默认不变。
- 测试：`tests/unit/` 新增字段默认、agent 配置解析、client 用 per-server 超时（mock httpx 捕获 timeout）用例。
- 不在范围（记为未来）：Platform DB 列 + admin API 持久化（需 Alembic 迁移，单独立项）；`resetTimeoutOnProgress`（fleetent 的 HTTP 传输为非流式请求/响应，进度重置需流式读改造，宜与未来 Streamable HTTP 流恢复一并做）。
- 依赖/外部系统：无新增依赖，不触碰 `data/`。
