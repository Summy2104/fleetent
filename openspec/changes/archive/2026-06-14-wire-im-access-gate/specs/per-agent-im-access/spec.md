# per-agent-im-access Delta

## MODIFIED Requirements

### Requirement: Runtime access gate reads per-connector access config
The agent runtime SHALL resolve the `ConnectorAccess` for an incoming message by matching `msg.platform` to the corresponding connector's `access` field; when no matching connector is found, a default-closed `ConnectorAccess()` SHALL apply. The gate SHALL branch by **conversation type** (`chat_type`):
- **DM**: admission requires `supports_dm` to be true AND the user gate to pass (user ∈ `allow_users`, or locally approved, or `allow_all_users`); otherwise the message is rejected.
- **Group/channel**: admission requires `supports_groups` to be true AND the group to be in the access group allowlist (the `allow_channels` field); a listed group grants implicit access to its members (group single-gate, user gate skipped).

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
- **THEN** default-closed `ConnectorAccess()` applies and the message is rejected

### Requirement: Channel listing grants implicit user access
The access group allowlist (the `allow_channels` field — renamed to `allow_groups` in a later phase) SHALL gate **group** messages only (DMs are not gated by it). When a group is explicitly listed, the agent SHALL admit its members without requiring them in `allow_users` (group single-gate). When the group allowlist is **empty**, the agent SHALL admit **no** group messages (default-closed). This reverses the prior "empty = allow all channels" behavior — an agent can no longer be pulled into arbitrary groups.

#### Scenario: User in listed group bypasses user gate
- **WHEN** the group allowlist contains group `C1` and a message arrives from `C1` from a user not in `allow_users`
- **THEN** the message proceeds (group single-gate), provided `supports_groups` is true

#### Scenario: Empty group allowlist admits no groups (default-closed)
- **WHEN** the group allowlist is empty and a group message arrives
- **THEN** the message is rejected (the agent is not in any group)

#### Scenario: Group allowlist does not affect DMs
- **WHEN** a DM arrives
- **THEN** the group allowlist is not consulted; admission is decided by `supports_dm` + the user gate

## ADDED Requirements

### Requirement: IM access config materialized from platform tables
The platform SHALL materialize the per-agent IM access config into the agent home from platform tables: `allow_users` from `user_agents`, the group allowlist from `agent_im_groups` (grouped by platform), and `supports_dm`/`supports_groups` from `agents`. This replaces the prior default-closed placeholder. Hand-authored connector credentials (e.g. `bot_token_env`) supplied via `config_overrides` SHALL be preserved (deep-merged, not overwritten by materialization).

#### Scenario: Access fields populated from platform tables
- **WHEN** an agent has `user_agents` rows, `agent_im_groups` rows, and `agents.supports_groups=1`, and is materialized
- **THEN** its agent home access config reflects those users / groups / capability, not the default placeholder

#### Scenario: Authored credentials preserved through materialization
- **WHEN** an agent's `config_overrides` carries a connector `bot_token_env` and materialization populates access fields
- **THEN** the materialized agent.yaml retains the authored `bot_token_env` (access fields merged without clobbering credentials)
