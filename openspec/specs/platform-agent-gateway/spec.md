## ADDED Requirements

### Requirement: Platform ingress for agent chat and WebSocket gateway

The platform SHALL expose operator ingress for managed agents at
`POST /admin/agents/{name}/chat` and `/admin/agents/{name}/ws`, authenticated as an
admin operator via session token. The platform SHALL look up the hosting node by
agent→node placement and SHALL be the only externally exposed surface; agents and node
forwarders SHALL NOT be exposed directly.

#### Scenario: Operator chats with a managed agent through the platform

- **WHEN** an authenticated admin sends a message to `/admin/agents/{name}/chat` for an
  agent placed on a node
- **THEN** the platform routes to that node and returns the agent response as a stream

#### Scenario: Unplaced or unknown agent

- **WHEN** the target agent is not placed on any node, or does not exist
- **THEN** the platform returns a clear not-available error and does not hang

#### Scenario: Non-admin denied at the front door

- **WHEN** a non-admin or unauthenticated caller hits the ingress
- **THEN** the platform returns 401/403 and does not forward

### Requirement: AgentTransport abstraction with DirectHttp implementation

The platform SHALL reach a node-hosted agent through an `AgentTransport` abstraction
whose contract supports a request producing a streaming response. This change SHALL
provide a `DirectHttp` implementation that dials the node forwarder. The seam SHALL allow
an alternative reverse-channel implementation later without changing ingress, routing, or
agent gateway behavior.

承载流式中继的 HTTP client（及其连接池）MUST 存活到被中继的流被**完整消费**之后；transport
MUST NOT 在返回流式响应的函数作用域退出时关闭该 client（例如不得用 `async with
httpx.AsyncClient()` 包裹一个在函数返回后才被迭代的流）。否则流在被消费前连接已关，operator
会收到空体或截断。

#### Scenario: DirectHttp reaches the forwarder

- **WHEN** the platform forwards an ingress request via the DirectHttp transport
- **THEN** it dials the target node forwarder authenticated by the node key and relays
  the streamed response back to the operator

#### Scenario: Streaming contract is preserved

- **WHEN** an agent emits a streamed reply
- **THEN** the transport relays chunks incrementally instead of buffering them into a
  single blob

#### Scenario: 承载 client 存活到流消费完毕

- **WHEN** transport 返回一个流式响应、其底层 HTTP client 在请求处理函数返回后才被消费
- **THEN** operator 收到 agent 的**完整**流（与直连 agent 一致），而非因 client 提前关闭导致
  的空体 / `ReadError` / 截断

### Requirement: Node internal forwarder

The node SHALL run an internal-only HTTP forwarder, authenticated by the node key, that
relays a platform request to the target local agent loopback gateway port and injects
that agent's `FLEETENT_TUI_TOKEN` from the managed `.env`. Agents SHALL bind loopback
only and SHALL NOT be exposed beyond the node.

forwarder 中继流式响应时，承载该流的 HTTP client（及其连接池）MUST 存活到流被**完整消费**之后；
forwarder MUST NOT 在返回 `StreamingResponse` 的处理函数作用域退出时关闭该 client。成功的流式
路径 MUST 把 agent 的完整响应逐块转发回上游；仅在上游返回错误状态（`status_code >= 400`）时
才允许整体 buffer 后返回。

#### Scenario: Forwarder relays to the local agent

- **WHEN** the forwarder receives a node-key-authenticated request for an agent
- **THEN** it forwards to that agent's loopback gateway port with that agent's
  `FLEETENT_TUI_TOKEN` injected, and relays the streamed response

#### Scenario: Forwarder rejects unauthenticated callers

- **WHEN** a request without a valid node key hits the forwarder
- **THEN** it is rejected and not forwarded

#### Scenario: forwarder 完整转发流式 body

- **WHEN** agent 在 loopback 端口对 forwarder 的转发请求返回多块 SSE 流
- **THEN** forwarder 把全部块逐块转发回上游、不丢失，operator 收到非空的完整流（不因承载
  client 在处理函数返回时被关闭而中继到 0 字节）

### Requirement: Node launches managed agents with a loopback gateway port

The node supervisor SHALL launch each managed agent bound to a loopback gateway port and
SHALL record that port so the forwarder can route to it. The port SHALL NOT be exposed
outside the node.

#### Scenario: Managed agent gets a loopback port

- **WHEN** the node starts a placed agent
- **THEN** the agent serves `/chat` and `/ws` on a loopback port and the node records the
  agent→port mapping for forwarding
