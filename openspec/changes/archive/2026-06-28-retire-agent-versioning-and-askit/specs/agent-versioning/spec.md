# agent-versioning

## ADDED Requirements

### Requirement: Agent configuration is stored as a single current state
The system SHALL keep each agent's configuration on the `agents` row as the only current-state source of truth. The management schema SHALL NOT use an `agent_versions` table or `agents.active_version_id`, and the admin API SHALL NOT expose version listing or activation endpoints.

#### Scenario: Head schema has no version table
- **WHEN** the management database is migrated to head
- **THEN** there is no `agent_versions` table
- **AND** the `agents` table has no `active_version_id` column

#### Scenario: Console edit updates current state in place
- **WHEN** an admin updates an agent configuration
- **THEN** the `agents` row is updated in place
- **AND** no version-history API is available
