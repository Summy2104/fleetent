## ADDED Requirements

### Requirement: Streamable HTTP 传输接入服务注册

平台 SHALL 支持以 `transport: http`（标准 Streamable HTTP）声明的远程 MCP 服务；该传输 MUST 经既有的服务注册分派接入，注册成功后其工具 MUST 以 `{server_id}__{tool_name}` 命名空间注册进工具表，与 stdio 传输的命名约定一致。

#### Scenario: 标准服务工具按命名空间注册
- **WHEN** 配置声明一个 `transport: http` 的 MCP 服务并启动注册
- **THEN** 该服务返回的每个工具以 `{server_id}__{tool_name}` 形式注册进工具表，可被 agent 调用

#### Scenario: stdio 传输行为不变
- **WHEN** 配置中存在 `transport: stdio` 的服务
- **THEN** 该类服务沿用原有注册与调用路径，行为与现状一致，不受标准 HTTP 传输引入影响

### Requirement: initialize 握手与会话标识管理

标准传输在注册时 SHALL 先发起 `initialize` 握手再列举工具。若 `initialize` 响应携带 `Mcp-Session-Id` 响应头，平台 MUST 保存该会话标识，并在同一服务后续的 `tools/list` 与 `tools/call` 请求头中回携该标识。会话标识 MUST 按服务隔离持有，不得置于模块级可变全局状态。

#### Scenario: 保存并回携会话标识
- **WHEN** 某 `http` 服务的 `initialize` 响应返回 `Mcp-Session-Id` 头
- **THEN** 该服务后续的工具列举与工具调用请求头携带相同的 `Mcp-Session-Id`

#### Scenario: 服务端未分配会话标识
- **WHEN** `initialize` 响应不含 `Mcp-Session-Id` 头
- **THEN** 后续请求不携带 `Mcp-Session-Id` 头，注册与调用仍正常进行

### Requirement: Accept 协商与 JSON/SSE 双响应解析

标准传输的每个请求 SHALL 在请求头声明同时接受 `application/json` 与 `text/event-stream`。平台 MUST 根据响应的 `Content-Type` 解析结果：`application/json` 时直接解析响应体的 JSON-RPC 对象；`text/event-stream` 时解析 SSE 事件，提取其中承载本次请求 JSON-RPC 响应的数据并还原为结果。

#### Scenario: 服务端返回 JSON 响应
- **WHEN** 某工具调用的响应 `Content-Type` 为 `application/json`
- **THEN** 平台从响应体解析 JSON-RPC 结果并将工具结果文本返回给调用方

#### Scenario: 服务端返回 SSE 响应
- **WHEN** 某工具调用的响应 `Content-Type` 为 `text/event-stream`，其 `data:` 行承载对应本次请求的 JSON-RPC 响应
- **THEN** 平台解析 SSE 事件、取出该 JSON-RPC 响应并将工具结果文本返回给调用方

### Requirement: 单调递增请求 id 与响应匹配

标准传输的每次 JSON-RPC 请求 SHALL 使用单调递增的请求 id，不得固定为同一值。当 SSE 响应包含多个事件时，平台 MUST 仅采纳 id 等于本次请求 id 的 JSON-RPC 响应对象。请求 id 计数 MUST 按服务隔离，不得置于模块级可变全局状态。

#### Scenario: SSE 夹带额外事件时取本次响应
- **WHEN** SSE 流中除本次请求的响应外还包含其他事件
- **THEN** 平台仅采纳 id 与本次请求一致的 JSON-RPC 响应，忽略其余事件

#### Scenario: 连续请求使用递增 id
- **WHEN** 对同一服务连续发起多次请求
- **THEN** 各次请求使用不同且递增的 id，互不冲突

### Requirement: 连接失败降级

`transport: http` 服务在注册（握手或工具列举）阶段连接失败时，平台 MUST 沿用既有的启动降级语义：记录告警、该服务工具不可用，且不阻断平台启动与其他服务注册。

#### Scenario: 单个标准服务握手失败不影响平台启动
- **WHEN** 配置了两个服务，其中一个 `transport: http` 服务在 `initialize` 阶段不可达
- **THEN** 平台正常完成启动，失败服务的工具不可用并记录告警，另一服务正常注册
