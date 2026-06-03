# agent-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Agents management tab
The admin console SHALL present an Agents tab listing each agent with its status, and SHALL list available agent templates. Write controls SHALL be admin-only. The New-agent modal SHALL use the wide modal box and, in create mode only, SHALL present a required template `<select>` populated from `GET /admin/agent-templates`; selecting a template SHALL prefill the system prompt and allowed tools, and the create request SHALL include the chosen `template_id`. Saving a new agent without a selected template SHALL be blocked client-side. The agent modal SHALL expose only the template-backed editable fields — `system_prompt` and `allowed_tools` (plus the agent `name` and template on create) — and SHALL NOT present `skills_dir`, `mcp_server_ids`, `model_overrides`, or `memory_namespace` inputs; create and edit requests SHALL omit those fields so they fall back to defaults or inherit the prior version.

#### Scenario: Admin sees agents and templates
- **WHEN** an admin opens the Agents tab
- **THEN** agents are listed via `GET /admin/agents` and templates via `GET /admin/agent-templates`

#### Scenario: Viewer cannot mutate agents
- **WHEN** a viewer opens the Agents tab
- **THEN** enable / disable / archive / restore / clone / bind controls are hidden

#### Scenario: New-agent modal requires a template
- **WHEN** an admin opens the New-agent modal
- **THEN** the modal uses the wide box and shows a required template `<select>` populated from the templates endpoint
- **AND** attempting to save without choosing a template is blocked
- **AND** choosing a template prefills the system prompt and allowed tools and sends `template_id` on create

#### Scenario: Modal exposes only template-backed fields
- **WHEN** an admin opens the New-agent or Edit-agent modal
- **THEN** only the `name`/template, `system_prompt`, and `allowed_tools` controls are present
- **AND** no `skills_dir`, `mcp_server_ids`, `model_overrides`, or `memory_namespace` input is shown
- **AND** saving sends only `system_prompt` and `allowed_tools` (plus `name`/`template_id` on create)

### Requirement: Agent lifecycle and clone
The console SHALL let an admin enable, disable, archive, restore, and clone an agent, and view observability, calling the matching endpoints. The per-row agent actions SHALL be collapsed into a single `⋯` overflow menu rather than rendered as a flat button row; admin-only items SHALL remain hidden for viewers. The overflow menu SHALL also offer a **Deploy** action that binds the agent to an IM channel (`platform` + `channel_id`) via the existing channel-binding endpoint, putting the agent live on that channel.

#### Scenario: Clone an agent
- **WHEN** an admin clones an agent
- **THEN** the console calls `POST /admin/agents/{name}/clone` and the new agent appears

#### Scenario: Row actions live in an overflow menu
- **WHEN** an admin views the agents list
- **THEN** each row's actions are reached through a `⋯` overflow menu (not a flat row of buttons)
- **AND** the menu contains the existing actions (stats, versions, edit, bindings, clone, enable/disable, archive/restore, delete)
- **AND** viewer sessions still hide the admin-only items

#### Scenario: Deploy an agent to a channel
- **WHEN** an admin chooses Deploy from the overflow menu and supplies a platform and channel_id
- **THEN** the console calls `POST /admin/agents/{name}/bindings/channels/{platform}/{channel}` to put the agent live on that channel

### Requirement: Agent versions and bindings
The console SHALL show an agent's versions and let an admin activate a version, and
bind/unbind users and channels. The Bindings modal SHALL additionally present a
**Skills** section, an **MCP** section, and a **Channels** list. The Skills section
SHALL load `GET /admin/agents/{name}/skills` and render a per-skill toggle that calls
`PUT /admin/agents/{name}/skills/{skill_name}`. The MCP section SHALL load options from
`GET /admin/mcp/servers` and the agent's current bindings from `GET
/admin/agents/{name}/bindings`, rendering per-server toggles that call `POST`/`DELETE
/admin/agents/{name}/bindings/mcp/{server_id}`. The Channels list SHALL render the
agent's bound channels (platform, channel_id, version) from `GET
/admin/agents/{name}/bindings` with a per-row unbind control. All binding write
controls SHALL be hidden from viewers.

#### Scenario: Activate a version
- **WHEN** an admin activates a listed version
- **THEN** the console calls `POST /admin/agents/{name}/versions/{version}/activate`

#### Scenario: Bind a user to an agent
- **WHEN** an admin binds a user to an agent
- **THEN** the console calls `POST /admin/agents/{name}/bindings/users/{user_id}`

#### Scenario: Toggle a skill binding from the agent

- **WHEN** an admin opens the Bindings modal and toggles a skill
- **THEN** the console calls `PUT /admin/agents/{name}/skills/{skill_name}` with the new enabled state

#### Scenario: Toggle an MCP binding from the agent

- **WHEN** an admin opens the Bindings modal and enables an MCP server
- **THEN** the console calls `POST /admin/agents/{name}/bindings/mcp/{server_id}` (and `DELETE` when disabling)

#### Scenario: Review and unbind channels

- **WHEN** an admin opens the Bindings modal
- **THEN** the agent's bound channels are listed from `GET /admin/agents/{name}/bindings`
- **AND** each row offers an unbind control calling `DELETE /admin/agents/{name}/bindings/channels/{platform}/{channel}`

#### Scenario: Viewer cannot mutate bindings

- **WHEN** a viewer opens the Bindings modal
- **THEN** the skill toggles, MCP toggles, and channel unbind controls are hidden

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

The admin console SHALL keep a single **Agents** sidebar item and surface **Agents** and **Templates** as two sub-tabs inside the Agents page header. Selecting the Templates sub-tab SHALL let an admin create, edit, and delete agent templates through a template modal capturing `id`, `display_name`, `allowed_tools`, and `system_prompt`. A "New template" control SHALL appear in the Templates sub-tab and per-template "Edit"/"Delete" actions SHALL appear in the templates list; all template write controls SHALL be hidden from viewers. There SHALL be no separate Templates sidebar nav item.

#### Scenario: Templates is an Agents-page sub-tab

- **WHEN** the admin opens the Agents tab
- **THEN** the page header shows `Agents` and `Templates` sub-tabs, there is no separate Templates sidebar nav item, and selecting the Templates sub-tab shows the templates list

#### Scenario: Admin creates a template

- **WHEN** an admin opens the Templates sub-tab, opens the template modal, fills id/display_name/allowed_tools/system_prompt, and saves
- **THEN** the console calls `POST /admin/agent-templates` and the new template appears in the list

#### Scenario: Admin edits a template

- **WHEN** an admin opens the edit action for a template, changes a field, and saves
- **THEN** the console calls `PATCH /admin/agent-templates/{id}` and the change is reflected

#### Scenario: Admin deletes a template

- **WHEN** an admin confirms deletion of a template
- **THEN** the console calls `DELETE /admin/agent-templates/{id}` and the template disappears from the list

#### Scenario: Viewer cannot edit templates

- **WHEN** a viewer opens the Templates sub-tab
- **THEN** the "New template" control and per-template Edit/Delete actions are hidden
