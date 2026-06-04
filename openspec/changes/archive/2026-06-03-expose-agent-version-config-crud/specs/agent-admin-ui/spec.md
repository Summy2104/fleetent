## MODIFIED Requirements

### Requirement: Agent create and edit

The Agents tab SHALL let an admin create a new agent and edit an existing one through a modal capturing `name`, `system_prompt`, `allowed_tools`, and the version-config fields `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`. A "New agent" control SHALL appear in the Agents bar and an "Edit" action SHALL appear in each agent row; both SHALL be hidden from viewers.

#### Scenario: Admin creates an agent

- **WHEN** an admin opens the create modal, fills name/system_prompt/allowed_tools (and optionally skills_dir/mcp_server_ids/model_overrides/memory_namespace), and saves
- **THEN** the console calls `POST /admin/agents` with the provided fields and the new agent appears in the list

#### Scenario: Admin edits an agent

- **WHEN** an admin opens the edit action for an agent, changes a field, and saves
- **THEN** the console first reads `GET /admin/agents/{name}` to prefill all fields (including the version-config fields), then calls `PATCH /admin/agents/{name}`

#### Scenario: Modal exposes version-config inputs

- **WHEN** an admin opens the create or edit modal
- **THEN** the modal presents inputs for `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace` in addition to `system_prompt` and `allowed_tools`

#### Scenario: Viewer cannot create or edit

- **WHEN** a viewer opens the Agents tab
- **THEN** the "New agent" control and per-row "Edit" action are hidden
