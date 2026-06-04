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

### Requirement: Runtime access gate is local and zero-DB

`normalizer.route` SHALL evaluate the channel and user gates against the agent's local
access config and local approval store, and SHALL NOT read `im_channel_allowlist` or the
owner-keyed user store on the runtime path.

#### Scenario: Allowed user proceeds

- **WHEN** a message arrives from a user in `access.allow_users` (or approved locally)
- **THEN** routing proceeds to the agent loop with no platform-DB lookup

#### Scenario: Disallowed user blocked locally

- **WHEN** a message arrives from a user not allowed and `require_approval` is set
- **THEN** the agent replies with the rejection/approval prompt and the message never
  reaches the loop, decided entirely from local state
