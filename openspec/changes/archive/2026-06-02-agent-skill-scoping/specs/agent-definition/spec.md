## MODIFIED Requirements

### Requirement: Agent definition storage
The system SHALL store agent definitions (name, system_prompt, allowed_tools, plugins, allowed_skills) in the `agents` SQLite table. The `plugins` field is a list of plugin names (default empty) declaring which plugins the agent is authorized to use; it is persisted as a JSON array text, mirroring `allowed_tools`. The `allowed_skills` field is a list of skill names (default empty) that narrows which skills appear in the agent's `<available_skills>` catalog; it is persisted as a JSON array text, mirroring `allowed_tools`. An empty `allowed_skills` means no narrowing (all enabled skills remain visible, preserving existing behavior) — the opposite default semantics from `plugins`, because skills are visible to every agent by default whereas plugin tools are not.

#### Scenario: Create agent
- **WHEN** admin CLI calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell","github__*"]'`
- **THEN** a row is inserted into `agents` with the given fields, and `plugins` and `allowed_skills` default to empty lists

#### Scenario: Create agent with plugins
- **WHEN** an agent is created with `plugins=["crm_tools"]`
- **THEN** the row stores `plugins` as `["crm_tools"]` and `get_by_name` reads it back unchanged

#### Scenario: Create agent with allowed_skills
- **WHEN** an agent is created with `allowed_skills=["weather"]`
- **THEN** the row stores `allowed_skills` as `["weather"]` and `get_by_name` reads it back unchanged

#### Scenario: Query agent by name
- **WHEN** an incoming message is associated with an agent named "assistant"
- **THEN** `agent_store.get_by_name("assistant")` returns the full agent definition including its `plugins` and `allowed_skills` lists

#### Scenario: Legacy row without plugins
- **WHEN** an existing `agents` row predates the `plugins` column
- **THEN** reading that agent yields `plugins == []` (backward compatible, no behavior change)

#### Scenario: Legacy row without allowed_skills
- **WHEN** an existing `agents` row predates the `allowed_skills` column
- **THEN** reading that agent yields `allowed_skills == []` (backward compatible: empty means no narrowing, all enabled skills visible)

### Requirement: Schema
The `agents` table SHALL store: `id`, `name` (UNIQUE), `system_prompt`, `allowed_tools` (JSON array text), `plugins` (JSON array text, default `[]`), `allowed_skills` (JSON array text, default `[]`), `created_at`.
The `user_agents` table SHALL store: `user_id` (→ users.id), `agent_id` (→ agents.id), with PRIMARY KEY on `(user_id, agent_id)`.

#### Scenario: Duplicate agent name rejected
- **WHEN** admin tries to create an agent with a name that already exists
- **THEN** the database UNIQUE constraint prevents it and an error is returned

#### Scenario: Plugins column defaults for existing rows
- **WHEN** the `plugins` column is added to a table that already contains agent rows
- **THEN** existing rows take the `[]` default and remain readable without error

#### Scenario: allowed_skills column defaults for existing rows
- **WHEN** the `allowed_skills` column is added (alembic 004) to a table that already contains agent rows
- **THEN** existing rows take the `[]` default and remain readable without error
