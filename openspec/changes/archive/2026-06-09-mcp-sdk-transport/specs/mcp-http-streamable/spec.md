## MODIFIED Requirements

### Requirement: Streamable HTTP 传输经官方 SDK 接入服务注册

平台 SHALL 支持以 `transport: http`（Streamable HTTP）与 `transport: sse`（旧式 SSE）声明的远程 MCP 服务,经官方 `mcp` SDK 的 `streamablehttp_client` / `sse_client` 建立传输、产出 `(read, write)` 流并喂给 `ClientSession`。注册成功后其工具 MUST 以 `{server_id}__{tool_name}` 命名空间注册进工具表,与 stdio 传输的命名约定一致。

#### Scenario: 标准服务工具按命名空间注册
- **WHEN** 配置声明一个 `transport: http` 的 MCP 服务并启动注册
- **THEN** 平台经 SDK `streamablehttp_client` + `ClientSession` 完成注册,该服务每个工具以 `{server_id}__{tool_name}` 形式注册进工具表,可被 agent 调用

#### Scenario: SSE 传输按命名空间注册
- **WHEN** 配置声明一个 `transport: sse` 的 MCP 服务并启动注册
- **THEN** 平台经 SDK `sse_client` + `ClientSession` 完成注册,工具同样以命名空间注册

#### Scenario: stdio 传输行为不变
- **WHEN** 配置中存在 `transport: stdio` 的服务
- **THEN** 该类服务沿用既有的 SDK `stdio_client` + `ClientSession` 路径,行为不变

### Requirement: 握手、会话标识、协议协商、SSE 解析委托给 SDK

`initialize` 握手、`Mcp-Session-Id` 会话标识的捕获与回携、`Accept` 协商、JSON / SSE 响应解析、单调递增请求 id 与响应匹配、协议版本协商——全部 MUST 由官方 SDK 的传输层与 `ClientSession` 内部处理,平台 MUST NOT 自行手写这些协议细节。平台持有 SDK 返回的 `ClientSession`(按服务隔离,见会话生命周期),经其 `list_tools()` / `call_tool()` 方法收发,不直接构造 JSON-RPC 请求体或解析 SSE 事件。

#### Scenario: 协议细节由 SDK 处理
- **WHEN** 某 `http` 服务完成注册并调用工具
- **THEN** 握手、会话标识管理、Accept 协商、SSE/JSON 解析、请求 id 匹配均由 SDK 完成,平台仅调用 `ClientSession.call_tool()` 并消费返回的结构化结果

#### Scenario: 工具列举经 SDK 分页
- **WHEN** 某服务的 `tools/list` 跨多页(SDK 返回 nextCursor)
- **THEN** 平台经 `ClientSession.list_tools(cursor=…)` 循环取尽各页(封顶页数防失控),聚合注册

### Requirement: 自定义 HTTP headers 经 SDK transport 透传

HTTP/SSE 传输的 MCP 服务 SHALL 支持在 agent 配置中声明任意自定义 header(`mcp_servers[*].headers`),平台 MUST 在解析 `env:VAR_NAME` 引用后,将其作为 `headers=` 参数传给 SDK 的 `streamablehttp_client` / `sse_client`,由 SDK 并入每个请求。header 值为 `env:VAR_NAME` 形式时 MUST 解析为进程环境真实值,绝不发送字面 `env:VAR_NAME`。

#### Scenario: 自定义 header 经 SDK 发送
- **WHEN** 某 `transport: http` 服务声明 `headers: {X-API-Key: "literal-key"}`
- **THEN** 平台将其作为 `headers=` 传给 SDK transport,该服务请求头携带 `X-API-Key: literal-key`

#### Scenario: header 值的 env: 引用被解析
- **WHEN** 某服务声明 `headers: {X-API-Key: env:MIDDLE_KEY}` 且 `MIDDLE_KEY` 已在进程环境设置
- **THEN** 传给 SDK 的 header 值为 `MIDDLE_KEY` 的解析值,而非字面 `env:MIDDLE_KEY`

### Requirement: 连接失败降级

`transport: http` / `sse` 服务在注册(握手或工具列举)阶段连接失败时,平台 MUST 沿用既有启动降级语义:记录告警、该服务工具不可用、不阻断平台启动与其他服务注册。

#### Scenario: 单个服务握手失败不影响平台启动
- **WHEN** 配置了两个服务,其中一个 `transport: http` 服务在注册阶段不可达
- **THEN** 平台正常完成启动,失败服务工具不可用并记录告警,另一服务正常注册

## REMOVED Requirements

### Requirement: Accept 协商与 JSON/SSE 双响应解析

**Reason**: 由官方 SDK 传输层内部处理,平台不再手写 SSE 解析与 Content-Type 分支。
**Migration**: 行为等价并入「握手、会话标识、协议协商、SSE 解析委托给 SDK」要求,无配置变化。

### Requirement: 单调递增请求 id 与响应匹配

**Reason**: JSON-RPC 请求 id 生成与响应匹配由 SDK `ClientSession` 内部处理。
**Migration**: 并入 SDK 委托要求,无配置变化。

### Requirement: initialize 握手与会话标识管理

**Reason**: `initialize` 与 `Mcp-Session-Id` 由 SDK 传输层 + `ClientSession` 管理。
**Migration**: 会话标识改为随 SDK `ClientSession` 持有(见 mcp-session-continuity「会话生命周期按服务隔离持有」),无配置变化。

### Requirement: HTTP 请求 URL 原样发送

**Reason**: URL 直接传给 SDK `streamablehttp_client(url=…)`,SDK 按配置原样使用,不再有平台手写的尾斜杠拼接。
**Migration**: 行为不变(SDK 不强加尾斜杠),配置 `url` 写法不变。
