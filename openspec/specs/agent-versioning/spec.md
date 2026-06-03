# agent-versioning Specification

## Purpose
TBD - created by archiving change 2026-05-29-multi-agent-management. Update Purpose after archive.
## Requirements
### Requirement: agent_versions table schema
The system SHALL store immutable agent version snapshots in an `agent_versions` SQLite table. Each row SHALL hold `id`, `agent_id` (→ agents.id), `version` (monotonic per agent_id), `system_prompt`, `allowed_tools` (JSON array), `skills_dir` (nullable), `mcp_server_ids` (JSON array), `model_overrides` (JSON object), `memory_namespace`, `created_at`, and optional `created_by_user_id`. `(agent_id, version)` SHALL be UNIQUE.

#### Scenario: First version created with the agent
- **WHEN** `agent_store.create_agent(name=..., system_prompt=..., allowed_tools=[...])` is called
- **THEN** a row in `agents` AND a row in `agent_versions` with `version=1` are inserted in the same transaction
- **AND** `agents.active_version_id` points to the new version row

#### Scenario: New version increments monotonically
- **WHEN** `agent_store.create_version(name, system_prompt=..., ...)` is called on an agent that already has versions 1 and 2
- **THEN** a new `agent_versions` row is inserted with `version=3`

### Requirement: Active version pointer is single source of truth
The `agents.active_version_id` column SHALL determine which version is returned by default lookups. Switching active version SHALL be a single atomic `UPDATE` statement.

#### Scenario: get_by_name returns active version content
- **WHEN** an agent has versions 1, 2, 3 and `active_version_id` points to version 2
- **THEN** `agent_store.get_by_name(name)` returns a structure containing version 2's `system_prompt` and `allowed_tools`

#### Scenario: Activating a different version is atomic
- **WHEN** `agent_store.activate_version(name, version=1)` is called while version 3 is active
- **THEN** after the call, `active_version_id` references version 1 and any new request resolves to version 1's snapshot

### Requirement: Versions are immutable
Once written, an `agent_versions` row SHALL NOT be modified. Edits SHALL always create a new version row.

#### Scenario: PATCH never overwrites
- **WHEN** an admin attempts to "update" an agent's `system_prompt`
- **THEN** a new `agent_versions` row is inserted, the old row remains unchanged, and `active_version_id` either is updated to the new version or left pointing at the previous version depending on call site

### Requirement: AgentSnapshot is the runtime representation
`agent_runtime.AgentSnapshot` SHALL be a frozen dataclass holding `agent_id`, `agent_name`, `version`, `version_id`, `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`.

#### Scenario: load_active returns snapshot of active version
- **WHEN** `agent_runtime.load_active(name)` is called for an existing agent
- **THEN** an `AgentSnapshot` populated from the active `agent_versions` row is returned

#### Scenario: load_version returns specific historical version
- **WHEN** `agent_runtime.load_version(name, version=2)` is called
- **THEN** a snapshot reflecting version 2's contents is returned regardless of which version is active

#### Scenario: Snapshot for missing agent
- **WHEN** `agent_runtime.load_active("nonexistent")` is called
- **THEN** `None` is returned and no exception is raised

### Requirement: Session locks to its initial snapshot
When a session is created the system SHALL persist the `agent_version_id` selected at that moment. Subsequent turns in the same session SHALL use that exact version, even if `active_version_id` changes mid-session.

#### Scenario: Active version changes during a live session
- **WHEN** a session is started under version 2 and `activate_version(name, version=3)` is called before the next turn
- **THEN** the next turn of the same session continues to use version 2

#### Scenario: New session after version change picks up the new active
- **WHEN** version 3 is active and a brand-new session begins
- **THEN** the session is bound to version 3 and persists `version_id=<v3 id>` in its metadata

### Requirement: Backfill version 1 for pre-existing agents
On schema upgrade, every existing agent row that lacks an `active_version_id` SHALL be backfilled with a synthetic version 1 mirroring its current `system_prompt` and `allowed_tools`. To preserve prior behavior the backfilled version SHALL set `mcp_server_ids = NULL` (interpreted at runtime as "no MCP restriction" so existing agents keep access to all MCP tools), `skills_dir = NULL`, `model_overrides = {}`, and `memory_namespace = "default"`.

#### Scenario: Idempotent backfill on migration
- **WHEN** the Alembic upgrade runs against a database where `agents` rows exist with `active_version_id IS NULL`
- **THEN** for each such row a new `agent_versions(version=1)` row is inserted carrying the pre-change fields with `mcp_server_ids = NULL`, and `active_version_id` is set; re-running the data migration performs no further mutations

