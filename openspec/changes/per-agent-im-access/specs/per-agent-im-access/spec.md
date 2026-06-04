## ADDED Requirements

### Requirement: Per-agent IM access config in the agent home

An agent SHALL carry its IM access rules in its home configuration: an `access` block
with `allow_channels` (list), `allow_users` (list), and `require_approval` (bool). These
rules SHALL be read from the agent home, not from an owner-keyed platform table.

#### Scenario: Access rules loaded from the agent home

- **WHEN** an agent home declares `access.allow_users: ["u_alice"]` and the agent loads
- **THEN** the resolved agent exposes that allow rule for runtime evaluation, with no
  platform-DB read

#### Scenario: Absent access block defaults to closed-with-approval

- **WHEN** an agent home has no `access` block
- **THEN** the agent applies a safe default (no implicit allow; approval required) rather
  than allowing everyone

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

### Requirement: Runtime access gate is local and zero-DB

The agent runtime SHALL evaluate the channel and user gates against the agent's local
access config and local approval store via the `im` module, and SHALL NOT read the
owner-keyed channel allowlist or user store on the runtime path.

#### Scenario: Allowed user proceeds

- **WHEN** a message arrives from a user in `access.allow_users` (or approved locally)
- **THEN** routing proceeds to the agent loop with no platform-DB lookup

#### Scenario: Disallowed user blocked locally

- **WHEN** a message arrives from a user not allowed and `require_approval` is set
- **THEN** the agent replies with the rejection/approval prompt and the message never
  reaches the loop, decided entirely from local state
