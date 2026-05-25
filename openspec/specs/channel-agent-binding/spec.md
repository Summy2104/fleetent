# channel-agent-binding Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
### Requirement: Channel-to-agent binding storage
The system SHALL store channel-to-agent bindings in a `channel_agents` table keyed by `(platform, channel_id)`.

#### Scenario: Create binding
- **WHEN** admin runs `fleetent-admin assign-channel --platform slack --channel-id C123456 --agent-name assistant`
- **THEN** a row is inserted into `channel_agents(platform="slack", channel_id="C123456", agent_id=<assistant's id>)`

#### Scenario: Duplicate binding is replaced
- **WHEN** a binding already exists for `(platform, channel_id)` and admin assigns a different agent
- **THEN** the old binding is replaced (upsert semantics)

#### Scenario: Remove binding
- **WHEN** admin runs `fleetent-admin unassign-channel --platform slack --channel-id C123456`
- **THEN** the row for `("slack", "C123456")` is deleted from `channel_agents`

#### Scenario: Channel not bound
- **WHEN** no row exists for the given `(platform, channel_id)`
- **THEN** `agent_store.get_agent_for_channel(platform, channel_id)` returns `None`

### Requirement: Channel binding takes priority over user binding in agent lookup
During message routing, the channel-level agent binding SHALL be checked before the user-level binding.

#### Scenario: Message in channel with binding
- **WHEN** a message arrives in a channel that has a `channel_agents` binding
- **THEN** the channel's agent is used, regardless of whether the user has their own binding

#### Scenario: Message in channel without binding, user has binding
- **WHEN** a message arrives in an unbound channel but the user is bound to an agent
- **THEN** the user's agent is used

#### Scenario: Schema
- **WHEN** examining the `channel_agents` table
- **THEN** it has columns: `id`, `platform` (TEXT), `channel_id` (TEXT), `agent_id` (INTEGER → agents.id), `created_at`, with a UNIQUE constraint on `(platform, channel_id)`

