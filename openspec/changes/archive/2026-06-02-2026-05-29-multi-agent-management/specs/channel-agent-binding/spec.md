## MODIFIED Requirements

### Requirement: Channel-to-agent binding storage
The system SHALL store channel-to-agent bindings in a `channel_agents` table keyed by `(platform, channel_id)`. Each row SHALL also carry an audit-only `bound_version_id` recording which `agent_versions.id` was active at bind time. `bound_version_id` is informational and SHALL NOT lock the channel to that version; live channels track the agent's current `active_version_id` like before.

#### Scenario: Create binding records active version
- **WHEN** admin runs `fleetent-admin assign-channel --platform slack --channel-id C123456 --agent-name assistant`
- **AND** assistant's current active version is 5
- **THEN** a row is inserted into `channel_agents("slack", "C123456", agent_id, bound_version_id=<v5 id>, created_at=...)`

#### Scenario: Duplicate binding is replaced and audit field refreshed
- **WHEN** a binding already exists for `(platform, channel_id)` (with `bound_version_id` pointing at v5) and admin assigns a different agent whose active version is v2
- **THEN** the old binding is replaced (upsert semantics) and `bound_version_id` becomes the new agent's v2 id

#### Scenario: Live messages still follow the active version
- **WHEN** a channel was bound while v5 was active, and the agent's active version later becomes v7
- **THEN** new messages arriving in that channel are served by v7 (channel binding does NOT freeze the version)

#### Scenario: Remove binding
- **WHEN** admin runs `fleetent-admin unassign-channel --platform slack --channel-id C123456`
- **THEN** the row for `("slack", "C123456")` is deleted from `channel_agents`

#### Scenario: Channel not bound
- **WHEN** no row exists for the given `(platform, channel_id)`
- **THEN** `agent_store.get_agent_for_channel(platform, channel_id)` returns `None`

### Requirement: Channel binding takes priority over user binding in agent lookup
During message routing, the channel-level agent binding SHALL be checked before the user-level binding. The resolution returns the channel's agent at its CURRENT active version (not `bound_version_id`).

#### Scenario: Message in channel with binding
- **WHEN** a message arrives in a channel that has a `channel_agents` binding
- **THEN** the channel's agent is used, regardless of whether the user has their own binding

#### Scenario: Message in channel without binding, user has binding
- **WHEN** a message arrives in an unbound channel but the user is bound to an agent
- **THEN** the user's agent is used

## ADDED Requirements

### Requirement: channel_agents carries bound_version_id audit column
The `channel_agents` table SHALL have columns: `id`, `platform` (TEXT), `channel_id` (TEXT), `agent_id` (INTEGER → agents.id), `bound_version_id` (INTEGER → agent_versions.id, nullable for legacy rows), `created_at`, with UNIQUE constraint on `(platform, channel_id)`.

#### Scenario: Legacy row missing bound_version_id
- **WHEN** an existing row predates this change and has `bound_version_id IS NULL`
- **THEN** lookups still succeed and routing falls back to the agent's current active version
