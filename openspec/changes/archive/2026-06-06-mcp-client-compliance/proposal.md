## Why

接入真实 MCP 服务时，fleetent 的 client 有三处与协议/provider 不合规：(1) `tools/list` 不读 `nextCursor`，工具数超过一页的服务会被静默截断；(2) 服务端返回的输入 JSON Schema 原样塞给 LLM，某些 provider 对缺失 `type: object` 或 `definitions`（而非 `$defs`）的 schema 会 400；(3) 不捕获 `initialize` 返回的 `protocolVersion`/`capabilities`，也不按 MCP 2025-06-18 规范在后续 HTTP 请求回发 `MCP-Protocol-Version` header。

## What Changes

- **游标分页**：`tools/list` 在 http 与 stdio 两条路径（注册与 probe）按 `nextCursor` 循环抓取直至取尽；带页数上限保险，防服务端返回死循环游标。
- **输入 schema 净化**：注册工具前对服务端 `inputSchema` 做保守等价规范化——保证顶层 `type: "object"` 且含 `properties`；递归把 `definitions` 重命名为 `$defs` 并同步重写 `#/definitions/` 引用。不做高风险的 nullable union 折叠（记为未来增强）。
- **协议版本协商与回发**：`initialize` 后捕获服务端返回的 `protocolVersion` 与 `capabilities` 到 per-server 状态；HTTP 后续请求（initialize 之后）回发 `MCP-Protocol-Version` header。capabilities 捕获同时为后续 resources/prompts 变更打基础。

非破坏性：单页、已合规的服务行为不变。

## Capabilities

### New Capabilities
- `mcp-client-compliance`: 定义 MCP 客户端的工具发现完整性（分页）、provider 安全的输入 schema 规范化、协议版本协商与 `MCP-Protocol-Version` 回发、以及服务端能力捕获。

### Modified Capabilities
<!-- 无：现有 mcp-client / mcp-http-streamable spec 未对分页 / schema 净化 / 协议版本 header / 能力捕获作出要求，故为纯新增能力。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`——`_register_http_server`/`_register_stdio_server`/`_probe_*` 改为分页；`_register_tool_http`/`_register_tool_stdio` 注册前净化 schema；`_open_session` 与 stdio `initialize` 捕获版本/能力；`_base_headers` 回发 `MCP-Protocol-Version`；`McpServerConfig` 新增 `protocol_version`/`capabilities` 运行时字段。
- 行为：多页工具不再丢失；问题 schema 不再触发 provider 400；HTTP 请求符合 2025-06-18 版本头要求；能力信息可供后续 resources/prompts 门控。
- 测试：`tests/unit/` 新增分页、schema 净化、版本/能力捕获、header 回发用例（mock，无真实 I/O）。
- 依赖/外部系统：无新增依赖，不触碰 `data/`。
