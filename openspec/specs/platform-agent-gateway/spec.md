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

#### Scenario: DirectHttp reaches the forwarder

- **WHEN** the platform forwards an ingress request via the DirectHttp transport
- **THEN** it dials the target node forwarder authenticated by the node key and relays
  the streamed response back to the operator

#### Scenario: Streaming contract is preserved

- **WHEN** an agent emits a streamed reply
- **THEN** the transport relays chunks incrementally instead of buffering them into a
  single blob

### Requirement: Node internal forwarder

The node SHALL run an internal-only HTTP forwarder, authenticated by the node key, that
relays a platform request to the target local agent loopback gateway port and injects
that agent's `FLEETENT_TUI_TOKEN` from the managed `.env`. Agents SHALL bind loopback
only and SHALL NOT be exposed beyond the node.

#### Scenario: Forwarder relays to the local agent

- **WHEN** the forwarder receives a node-key-authenticated request for an agent
- **THEN** it forwards to that agent's loopback gateway port with that agent's
  `FLEETENT_TUI_TOKEN` injected, and relays the streamed response

#### Scenario: Forwarder rejects unauthenticated callers

- **WHEN** a request without a valid node key hits the forwarder
- **THEN** it is rejected and not forwarded

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
