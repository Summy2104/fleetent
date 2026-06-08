## MODIFIED Requirements

### Requirement: Per-agent IM access config in the agent home

An agent SHALL carry its IM access rules inside its connector declarations, not in a
top-level `access` block. Each connector (`connectors.slack`, `connectors.telegram`)
SHALL embed an `access: ConnectorAccess` object with `allow_channels` (list),
`allow_users` (list), and `require_approval` (bool). The runtime SHALL resolve access
policy by reading the connector that matches `msg.platform`, with zero platform-DB access.
The top-level `AgentFile.access` field and `AgentAccess` class are removed.

#### Scenario: Access rules loaded from the connector's access block

- **WHEN** an agent home declares `connectors.slack.access.allow_users: ["u_alice"]` and the agent loads
- **THEN** the resolved agent exposes that allow rule under `connectors.slack.access` for runtime evaluation, with no platform-DB read

#### Scenario: Absent access block defaults to closed-with-approval

- **WHEN** an agent home declares `connectors.slack` with no `access` sub-block
- **THEN** the agent applies a safe default (`ConnectorAccess()`: no implicit allow, approval required) for Slack messages

#### Scenario: Slack and Telegram can have independent access policies

- **WHEN** an agent declares `connectors.slack.access.allow_all_users: false` and `connectors.telegram.access.require_approval: false`
- **THEN** the runtime enforces the Slack policy for Slack messages and the Telegram policy for Telegram messages independently

### Requirement: Runtime access gate reads per-connector access config

The agent runtime SHALL resolve the `ConnectorAccess` for an incoming message by
matching `msg.platform` to the corresponding connector's `access` field. It SHALL NOT
read `AgentFile.access` (removed). When no matching connector is found, a default-closed
`ConnectorAccess()` SHALL be applied.

#### Scenario: Allowed user proceeds via connector access

- **WHEN** a Slack message arrives from a user in `connectors.slack.access.allow_users`
- **THEN** routing proceeds to the agent loop with no platform-DB lookup

#### Scenario: Disallowed user blocked by connector access

- **WHEN** a Slack message arrives from a user not in `allow_users` and not locally approved, and `require_approval` is set
- **THEN** the agent replies with the rejection message and the message never reaches the loop, decided entirely from local state

#### Scenario: Unknown platform falls back to default-closed

- **WHEN** a message arrives on a platform with no matching connector declaration
- **THEN** `ConnectorAccess()` is applied and the user is rejected (require_approval default)

## REMOVED Requirements

### Requirement: AgentBindings routing

**Reason**: `AgentBindings` (`bindings.channels`, `bindings.users`, `bindings.default`) was used to build a `by_channel`/`by_user` routing table in `AgentConfigIndex`. In per-agent connector deployments the agent is identified by the receiving connection, so this routing table is never consulted on the IM path. The field is removed to eliminate dead code and configuration confusion.

**Migration**: Remove `bindings:` blocks from `agent.yaml` files. Routing is implicit via the per-agent bot connection; no channel→agent mapping is needed.
