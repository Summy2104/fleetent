# per-agent-im-access Specification

## Purpose
Per-agent IM access control: a self-contained agent carries its own channel/user allow
rules and dynamic approvals in its home, so the agent runtime enforces access locally
with zero platform-database access. Created by archiving change per-agent-im-access.
## Requirements
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

### Requirement: Agent-local approval store

Runtime IM-user approvals SHALL be recorded in an agent-local store under the agent home
`data/`. A pending→approved transition SHALL write to this local store; the agent
runtime SHALL NOT write approvals to a platform database.

#### Scenario: Approval persists locally

- **WHEN** a user is approved at runtime for the agent
- **THEN** the approval is written to the agent's local store and survives a restart,
  with no platform-DB write

### Requirement: IM user identity resolved locally

The agent runtime SHALL resolve the IM user identity for a message without reading the
platform `user_store`: the (platform, platform_user_id) is mapped to the agent-runtime
identity using the platform-native id directly or an agent-local mapping store. No
platform-DB `get_or_create`/user lookup occurs on the runtime path.

#### Scenario: Identity resolved without platform user DB

- **WHEN** a Slack message arrives at the agent runtime and the platform `user_store` is
  rigged to raise on access
- **THEN** the message is still attributed to a stable per-agent identity and routing
  proceeds, proving identity resolution is local

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

### Requirement: Channel listing grants implicit user access

When a channel is explicitly listed in `access.allow_channels`, the agent SHALL allow all
users in that channel without requiring them to appear in `allow_users` or be locally
approved. The user gate SHALL be skipped for messages from explicitly listed channels.

When `allow_channels` is empty (allow-all-channels mode), no implicit user grant applies
and the user gate remains active.

#### Scenario: User in listed channel bypasses user gate

- **WHEN** `access.allow_channels: ["C1"]` and a message arrives from channel `C1` from
  a user not in `allow_users` and not locally approved
- **THEN** the message proceeds to the agent loop without rejection

#### Scenario: User in unlisted channel still requires authorization

- **WHEN** `access.allow_channels: ["C1"]` and a message arrives from channel `C2` from
  a user not in `allow_users`
- **THEN** the message is rejected (channel gate blocks it first)

#### Scenario: Empty allow_channels does not grant implicit channel access

- **WHEN** `access.allow_channels: []` (empty) and a message arrives from any channel
  from a user not in `allow_users` and not locally approved
- **THEN** the user gate is active and the message is rejected

### Requirement: allow_all_users flag opens access to all users

`ConnectorAccess` SHALL support an `allow_all_users: bool` field (default `false`). When
`true`, the user gate SHALL be skipped for all messages on this connector, including DMs.
`allow_users` entries and the local approval store are still valid but not consulted when
`allow_all_users` is set.

#### Scenario: allow_all_users true allows unknown DM user

- **WHEN** `access.allow_all_users: true` and a DM arrives from a user not in
  `allow_users` and not locally approved
- **THEN** the message proceeds to the agent loop without rejection

#### Scenario: allow_all_users false preserves existing gate behavior

- **WHEN** `access.allow_all_users: false` (default) and a user not in `allow_users`
  sends a message
- **THEN** the existing user gate applies (reject + add to pending if require_approval)

#### Scenario: allow_all_users default is false

- **WHEN** an agent declares a connector with no `allow_all_users` field
- **THEN** `allow_all_users` defaults to `false` and the user gate is active
