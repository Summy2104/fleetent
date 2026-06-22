# platform-agent-gateway Specification

## Purpose
Define the platform-side gateway for routing operator requests to node-hosted agents,
including ingress authentication, transport abstraction, node forwarder, and agent
loopback binding.
## Requirements
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

### Requirement: forwarder 地址解析可被环境覆盖

platform 拨 node forwarder 的地址默认 SHALL 为内网 DNS 契约 `<node_id>.internal`（生产内网解析）。
为支持无此 DNS 的部署形态（如单机 dev：所有组件在同一 loopback），地址解析 SHALL 可被环境变量
覆盖：当 override 设置时用之，未设置时回落到默认契约。该覆盖 MUST NOT 改变默认契约行为，也
MUST NOT 改变 forwarder 的 node-key 鉴权与路由语义。

#### Scenario: 默认用内网 DNS 契约

- **WHEN** 未设置 forwarder 地址 override
- **THEN** platform 按 `<node_id>.internal`（既有默认端口）解析 forwarder 地址

#### Scenario: 单机环境用 override 解析

- **WHEN** 设置了 forwarder 地址 override（如指向 `127.0.0.1`）
- **THEN** platform 按 override 解析 forwarder 地址，使无内网 DNS 的单机环境也能拨通 forwarder，
  鉴权与路由行为不变

### Requirement: Ingress carries the edge-resolved Principal end to end

托管 ingress SHALL 把**已解析的 `Principal{user_id, tenant_id}`**从解析它的 edge 端到端传到 agent：操作发起方（如 operator）的身份由平台/edge 解析，随转发（平台 → node forwarder → agent）承载，使 agent **按真实用户归属本回合**（会话/记忆/审批 scope by `Principal.user_id`），而非按传输鉴权 token 自身的 principal。

传输鉴权与用户身份 SHALL 分离：传输 token（node service key / `FLEETENT_TUI_TOKEN`）只证明**调用方是可信的 forwarder/TUI**；承载的 Principal 证明**是哪个用户**。承载的 Principal 仅因**传输已通过鉴权**才被信任（受信边界内传递）；未通过传输鉴权的调用 MUST NOT 能注入 Principal。

承载是**向后兼容**的：当入站未携带 Principal（如直连 TUI / 本地 dev），agent SHALL 回退到现行的自解析（按传输 token 解析 principal），standalone（无 platform）下行为不变。

#### Scenario: operator 身份到达 agent

- **WHEN** operator 经 `/admin/agents/{name}/chat`（admin session 已认证）发消息
- **THEN** 平台把 operator 解析成 Principal、随转发承载，agent 用**该 Principal**（operator 的 user_id）归属本回合，而非用传输 token 的 principal

#### Scenario: 跨租户仍被拒

- **WHEN** 承载的 `Principal.tenant_id` 与目标 agent 的租户不一致
- **THEN** agent 按既有 `_check_tenant` 返回 403，承载 Principal 不绕过租户校验

#### Scenario: 未鉴权调用不能注入身份

- **WHEN** 一个未通过传输鉴权（无有效 node key / TUI token）的调用尝试携带 Principal
- **THEN** 请求在传输鉴权处即被拒，承载的 Principal 不被信任、不生效

#### Scenario: 无承载 Principal 时回退自解析

- **WHEN** 入站未携带 Principal（直连 TUI / 本地 dev / standalone）
- **THEN** agent 回退到按传输 token 自解析 principal，行为与现状一致

### Requirement: 统一的 Principal-carrying agent 入站契约

agent 的入站（`/chat` 与 `/ws`）SHALL 接受一个统一形状的输入：可选的 edge 解析 `Principal` + `message`。该契约 SHALL 是后续各类 edge（IM、CLI、open-API 等）共同的目标形状——它们各自解析出 Principal 后产出相同载荷，复用同一条 forwarder→agent 脊柱。本要求**不规定**新增独立端点或端点改名（承载可扩展现有 `/chat`+`/ws`）。

#### Scenario: 多来源产出相同入站载荷

- **WHEN** 不同 edge（如平台 chat-edge）解析出 Principal 并发往 agent
- **THEN** agent 看到统一的 `{principal, message}` 入站形状，处理逻辑不因来源而分叉

