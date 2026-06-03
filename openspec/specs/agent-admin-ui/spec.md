# agent-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Agents management tab
The admin console SHALL present an Agents tab listing each agent with its status, and SHALL list available agent templates. Write controls SHALL be admin-only.

#### Scenario: Admin sees agents and templates
- **WHEN** an admin opens the Agents tab
- **THEN** agents are listed via `GET /admin/agents` and templates via `GET /admin/agent-templates`

#### Scenario: Viewer cannot mutate agents
- **WHEN** a viewer opens the Agents tab
- **THEN** enable / disable / archive / restore / clone / bind controls are hidden

### Requirement: Agent lifecycle and clone
The console SHALL let an admin enable, disable, archive, restore, and clone an agent, and view observability, calling the matching endpoints.

#### Scenario: Clone an agent
- **WHEN** an admin clones an agent
- **THEN** the console calls `POST /admin/agents/{name}/clone` and the new agent appears

### Requirement: Agent versions and bindings
The console SHALL show an agent's versions and let an admin activate a version, and bind/unbind users and channels.

#### Scenario: Activate a version
- **WHEN** an admin activates a listed version
- **THEN** the console calls `POST /admin/agents/{name}/versions/{version}/activate`

#### Scenario: Bind a user to an agent
- **WHEN** an admin binds a user to an agent
- **THEN** the console calls `POST /admin/agents/{name}/bindings/users/{user_id}`

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

### Requirement: Agent deletion

The Agents tab SHALL let an admin hard-delete an agent from a per-row "Delete" action, after an explicit confirmation, hidden from viewers.

#### Scenario: Admin deletes an agent

- **WHEN** an admin confirms deletion of an agent
- **THEN** the console calls `DELETE /admin/agents/{name}` with the confirmation header and the agent disappears from the list

#### Scenario: Viewer cannot delete

- **WHEN** a viewer opens the Agents tab
- **THEN** the per-row "Delete" action is hidden


### Requirement: Agent template editing

The admin console SHALL provide a dedicated **Templates** tab (under the Agents group) that lets an admin create, edit, and delete agent templates through a template modal capturing `id`, `display_name`, `allowed_tools`, and `system_prompt`. A "New template" control SHALL appear in the Templates tab and per-template "Edit"/"Delete" actions SHALL appear in the templates list; all template write controls SHALL be hidden from viewers. The Agents tab SHALL no longer contain template controls.

#### Scenario: Templates tab is a sibling of Agents

- **WHEN** the admin console renders the sidebar navigation
- **THEN** a `Templates` nav item (its own `#tab-templates` section) appears under the Agents group, separate from the Agents tab, and the Agents tab no longer shows a "Templates" toggle

#### Scenario: Admin creates a template

- **WHEN** an admin opens the Templates tab, opens the template modal, fills id/display_name/allowed_tools/system_prompt, and saves
- **THEN** the console calls `POST /admin/agent-templates` and the new template appears in the list

#### Scenario: Admin edits a template

- **WHEN** an admin opens the edit action for a template, changes a field, and saves
- **THEN** the console calls `PATCH /admin/agent-templates/{id}` and the change is reflected

#### Scenario: Admin deletes a template

- **WHEN** an admin confirms deletion of a template
- **THEN** the console calls `DELETE /admin/agent-templates/{id}` and the template disappears from the list

#### Scenario: Viewer cannot edit templates

- **WHEN** a viewer opens the Templates tab
- **THEN** the "New template" control and per-template Edit/Delete actions are hidden
