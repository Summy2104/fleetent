# per-agent-im-access Specification

## Purpose
Per-agent IM access control: a self-contained agent carries its own channel/user allow
rules and dynamic approvals in its home, so the agent runtime enforces access locally
with zero platform-database access. Created by archiving change per-agent-im-access.
## Requirements
### Requirement: Per-agent IM access config in the agent home
An agent SHALL carry its IM access rules inside its **`im`** binding declarations, not in a top-level `access` block. Each binding (**`im.slack`**, **`im.telegram`**) SHALL embed an **`access: ImAccess`** object with **`allow_groups`** (list), `allow_users` (list), and `require_approval` (bool); IM 能力 `supports_dm`/`supports_groups` 在顶层 `im` 上。The runtime SHALL resolve access policy by reading the binding that matches `msg.platform`, with zero platform-DB access. The top-level `AgentFile.access` field and `AgentAccess` class remain removed. （纯改名：`connectors`→`im`、`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups`；行为与阶段 3 完全一致。）

#### Scenario: Access rules loaded from the binding's access block
- **WHEN** an agent home declares `im.slack.access.allow_users: ["u_alice"]` and the agent loads
- **THEN** the resolved agent exposes that allow rule under `im.slack.access` for runtime evaluation, with no platform-DB read

#### Scenario: Absent access block defaults to closed-with-approval
- **WHEN** an agent home declares `im.slack` with no `access` sub-block
- **THEN** the agent applies a safe default (`ImAccess()`: no implicit allow, approval required) for Slack messages

#### Scenario: Slack and Telegram can have independent access policies
- **WHEN** an agent declares `im.slack.access.allow_all_users: false` and `im.telegram.access.require_approval: false`
- **THEN** the runtime enforces the Slack policy for Slack messages and the Telegram policy for Telegram messages independently

#### Scenario: 群白名单字段为 allow_groups
- **WHEN** an agent declares `im.slack.access.allow_groups: ["C1"]`
- **THEN** 群准入按该 `allow_groups` 列表判定（语义同阶段 3 的群白名单，仅字段名由 `allow_channels` 改为 `allow_groups`）

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
The agent runtime SHALL resolve the `ImAccess` for an incoming message by matching `msg.platform` to the corresponding connector's `access` field; when no matching connector is found, a default-closed `ImAccess()` SHALL apply. The gate SHALL branch by **conversation type** (`chat_type`):
- **DM**: admission requires `supports_dm` to be true AND the user gate to pass (user ∈ `allow_users`, or locally approved, or `allow_all_users`); otherwise the message is rejected.
- **Group/channel**: admission requires `supports_groups` to be true AND the group to be in the access group allowlist (the `allow_groups` field); a listed group grants implicit access to its members (group single-gate, user gate skipped).

`supports_dm` / `supports_groups` are agent-level capability flags (default `false`), materialized from `agents.supports_*`. With both defaulting false and no allowlists, a new agent admits nothing (default-closed).

#### Scenario: DM allowed when capability + user gate pass
- **WHEN** `supports_dm` is true and a DM arrives from a user in `allow_users`
- **THEN** routing proceeds to the agent loop, decided from local state with no platform-DB lookup

#### Scenario: DM rejected when capability off
- **WHEN** `supports_dm` is false and a DM arrives (even from an allowed user)
- **THEN** the message is rejected and never reaches the loop

#### Scenario: Group allowed when capability + group allowlist pass
- **WHEN** `supports_groups` is true and a message arrives in a group listed in the access group allowlist
- **THEN** the message proceeds (group single-gate: members are admitted without the user gate)

#### Scenario: Group rejected when capability off or group not listed
- **WHEN** `supports_groups` is false, OR the incoming group is not in the allowlist
- **THEN** the message is rejected

#### Scenario: Unknown platform falls back to default-closed
- **WHEN** a message arrives on a platform with no matching connector declaration
- **THEN** default-closed `ImAccess()` applies and the message is rejected

### Requirement: Channel listing grants implicit user access
The access group allowlist (the `allow_groups` field) SHALL gate **group** messages only (DMs are not gated by it). When a group is explicitly listed, the agent SHALL admit its members without requiring them in `allow_users` (group single-gate). When the group allowlist is **empty**, the agent SHALL admit **no** group messages (default-closed). This reverses the prior "empty = allow all channels" behavior — an agent can no longer be pulled into arbitrary groups.

#### Scenario: User in listed group bypasses user gate
- **WHEN** the group allowlist contains group `C1` and a message arrives from `C1` from a user not in `allow_users`
- **THEN** the message proceeds (group single-gate), provided `supports_groups` is true

#### Scenario: Empty group allowlist admits no groups (default-closed)
- **WHEN** the group allowlist is empty and a group message arrives
- **THEN** the message is rejected (the agent is not in any group)

#### Scenario: Group allowlist does not affect DMs
- **WHEN** a DM arrives
- **THEN** the group allowlist is not consulted; admission is decided by `supports_dm` + the user gate

### Requirement: allow_all_users flag opens access to all users

`ImAccess` SHALL support an `allow_all_users: bool` field (default `false`). When
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

### Requirement: IM access config materialized from platform tables
The platform SHALL materialize the per-agent IM access config into the agent home from platform tables: `allow_users` from `user_agents`, the group allowlist from `agent_im_groups` (grouped by platform), and `supports_dm`/`supports_groups` from `agents`. This replaces the prior default-closed placeholder. Hand-authored connector credentials (e.g. `bot_token_env`) supplied via `config_overrides` SHALL be preserved (deep-merged, not overwritten by materialization).

#### Scenario: Access fields populated from platform tables
- **WHEN** an agent has `user_agents` rows, `agent_im_groups` rows, and `agents.supports_groups=1`, and is materialized
- **THEN** its agent home access config reflects those users / groups / capability, not the default placeholder

#### Scenario: Authored credentials preserved through materialization
- **WHEN** an agent's `config_overrides` carries a connector `bot_token_env` and materialization populates access fields
- **THEN** the materialized agent.yaml retains the authored `bot_token_env` (access fields merged without clobbering credentials)

