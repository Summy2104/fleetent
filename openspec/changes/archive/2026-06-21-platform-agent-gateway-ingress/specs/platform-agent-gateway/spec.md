## ADDED Requirements

### Requirement: Platform ingress for agent chat/ws

The platform SHALL expose an operator ingress to converse with a managed agent — `POST /admin/agents/{name}/chat` and a `/admin/agents/{name}/ws` WebSocket — authenticated as an admin operator (session token). The platform SHALL route each request to the node that hosts the target agent, looked up via agent→node placement. The platform SHALL be the only externally exposed surface; agents and the node forwarder SHALL NOT be exposed directly.

#### Scenario: Operator chats with a managed agent through the platform

- **WHEN** an authenticated admin sends a message to `/admin/agents/{name}/chat` for an agent placed on a node
- **THEN** the platform routes to that node and returns the agent's response, streamed

#### Scenario: Unplaced or unknown agent

- **WHEN** the target agent is not placed on any node (or does not exist)
- **THEN** the platform returns a clear not-available error, not a hang

#### Scenario: Non-admin denied at the front door

- **WHEN** a non-admin (or unauthenticated) caller hits the ingress
- **THEN** the platform returns 401/403 and does not forward

### Requirement: AgentTransport abstraction with DirectHttp implementation

The platform SHALL reach a node-hosted agent through an `AgentTransport` abstraction whose contract supports a request producing a **streaming** response (WS/SSE). This change SHALL provide a `DirectHttp` implementation (platform dials the node forwarder). The seam SHALL allow an alternative reverse-channel implementation later **without** changing the ingress, routing, or agent gateway.

#### Scenario: DirectHttp reaches the forwarder

- **WHEN** the platform forwards an ingress request via the DirectHttp transport
- **THEN** it dials the target node's forwarder authenticated by the node key, and relays the streamed response back to the operator

#### Scenario: Streaming contract is preserved

- **WHEN** an agent emits a streamed reply
- **THEN** the transport relays chunks incrementally to the operator (not buffered to a single blob)

### Requirement: Node internal forwarder

The node SHALL run an internal-only HTTP forwarder, authenticated by the node key, that relays a platform request to the target local agent's loopback gateway port and injects that agent's `FLEETENT_TUI_TOKEN` (held by the node from the agent `.env` it manages). Agents SHALL bind loopback only and SHALL NOT be exposed beyond the node.

#### Scenario: Forwarder relays to the local agent

- **WHEN** the forwarder receives a node-key-authenticated request for agent X
- **THEN** it forwards to X's loopback gateway port with X's `FLEETENT_TUI_TOKEN` injected, and relays the streamed response

#### Scenario: Forwarder rejects unauthenticated callers

- **WHEN** a request without a valid node key hits the forwarder
- **THEN** it is rejected; the forwarder is never reachable outside the node's internal interface

### Requirement: Node launches agents with a loopback gateway port

The node supervisor SHALL launch each managed agent bound to a loopback gateway port and SHALL record that port so the forwarder can route to it. The port SHALL NOT be exposed outside the node.

#### Scenario: Managed agent gets a loopback port

- **WHEN** the node starts a placed agent
- **THEN** the agent serves `/chat`·`/ws` on a loopback port, and the node records the agent→port mapping for forwarding
