## ADDED Requirements

### Requirement: agent_versions records its originating template

The `agent_versions` table SHALL include a nullable `template_id` column recording the
agent template a version was created from. `agent_store.create_agent` SHALL accept an
optional `template_id` and persist it on the version-1 snapshot. `get_by_name` and the
`AgentVersion`/`Agent` structures SHALL expose `template_id`. New versions created by
`create_version` SHALL inherit the base version's `template_id` unless explicitly
overridden.

#### Scenario: create_agent persists template_id

- **WHEN** `agent_store.create_agent(name=..., system_prompt=..., allowed_tools=[...], template_id="support")` is called
- **THEN** the version-1 `agent_versions` row stores `template_id = "support"`
- **AND** `agent_store.get_by_name(name).template_id == "support"`

#### Scenario: create_agent without template_id stores NULL

- **WHEN** `agent_store.create_agent(name=..., system_prompt=..., allowed_tools=[...])` is called with no `template_id`
- **THEN** the version-1 row stores `template_id = NULL`
- **AND** `agent_store.get_by_name(name).template_id is None`

#### Scenario: new version inherits template_id

- **WHEN** an agent was created with `template_id="support"` and `create_version(name, system_prompt="new")` is called
- **THEN** the new version row retains `template_id = "support"`
