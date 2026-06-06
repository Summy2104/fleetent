## Context

`integrations/mcp/client.py`：http 注册经 `_register_http_server`（手写 JSON-RPC），stdio 经 `_register_stdio_server`（mcp SDK `ClientSession`）；admin probe 经 `_probe_http_tools`/`_probe_stdio_tools`。`_open_session` 发 initialize、存 `Mcp-Session-Id`，但 **丢弃** 解析出的 init result（含 `protocolVersion`/`capabilities`）。`_base_headers` 不含 `MCP-Protocol-Version`。工具注册时 `inputSchema` 原样使用。

## Goals / Non-Goals

**Goals:**
- 分页：两条传输、注册+probe 都按 `nextCursor` 取尽，带页数上限。
- schema 净化：保守等价变换（type:object+properties；definitions→$defs+ref 重写），不改语义、不抛。
- 协议版本：捕获服务端 `protocolVersion`（缺省回退客户端版本），HTTP 在 init 之后回发 `MCP-Protocol-Version`。
- 能力捕获：`capabilities` 存为 per-server dict，为后续 resources/prompts 门控铺路。

**Non-Goals:**
- nullable `anyOf` union 折叠等高风险 provider 适配（记为未来增强）。
- server→client 的 GET 流 / `Last-Event-ID` 流恢复（属后续变更）。
- 不改结果处理、降级、认证、超时逻辑。

## Decisions

**D1 分页助手。** 新增 `_list_all_tools_http(client, server)` 与 `_list_all_tools_stdio(session)`，循环 `tools/list`（http 传 `{"cursor": ...}`，stdio 传 `session.list_tools(cursor=...)`），累积 `tools` 直到无 `nextCursor`；以 `_MAX_TOOL_PAGES` 上限保险，命中则 `logger.warning` 并停。`_register_*`/`_probe_*` 改调这两个助手。理由：单点分页逻辑，注册与 probe 复用。

**D2 schema 净化保守。** `_sanitize_input_schema(schema)`：非 dict→`{"type":"object","properties":{}}`；保证顶层 `type:"object"`（缺则补）与 `properties`（缺则 `{}`）；递归 `_defs_rename`：把任意层的 `definitions` 键改名 `$defs`（若同层已存在 `$defs` 则不动，避免碰撞），把字符串 `$ref` 中的 `#/definitions/` 前缀改为 `#/$defs/`。只做语义等价变换，绝不抛（异常时回退原 schema）。在 `_register_tool_http`/`_register_tool_stdio` 注册前调用。

**D3 版本捕获 + header 时序。** `McpServerConfig` 新增 `protocol_version: str | None`、`capabilities: dict`（均 repr/compare=False 的运行时状态）。http：`_open_session` 解析 init result 后 `server.protocol_version = result.get("protocolVersion") or PROTOCOL_VERSION`、`server.capabilities = result.get("capabilities") or {}`。`_base_headers` 在 `server.protocol_version` 非空时加 `MCP-Protocol-Version`——因该值在 `_open_session` 末尾才置，故首个 initialize 请求不带（符合规范：版本头用于 init 之后），后续请求带。stdio：`session.initialize()` 返回 `InitializeResult`，用 `getattr` 取 `protocolVersion`/`capabilities`（pydantic 对象经 `model_dump` 转 dict 存储）。

**D4 能力存为 dict。** 统一存 dict：http 已是 dict；stdio 的 `ServerCapabilities` 经 `model_dump(exclude_none=True)`（容错：无 model_dump 时退回 `{}`）。理由：后续 Change（resources/prompts）跨传输按同一形态读 `capabilities.get("resources")`/`("prompts")`。

## Risks / Trade-offs

- definitions→$defs 重写若 schema 同时混用两者→只在同层无 `$defs` 时改名，避免覆盖；ref 重写按字符串前缀，安全幂等。
- 分页死循环→`_MAX_TOOL_PAGES` 上限 + 警告日志（不静默截断）。
- stdio `list_tools(cursor=...)`：依赖 SDK 接受 `cursor` kw；当前 `mcp` SDK 支持。首页 `cursor=None` 等价于无参调用。
- 版本头在 session rebuild 时其 initialize 会带上旧版本头——无害（服务端忽略/接受），rebuild 后重新捕获。
