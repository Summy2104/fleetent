# agent-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Agents management tab
The admin console SHALL present an Agents tab as a card grid (consistent with the Skills and Connectors modules), not a table. A toolbar SHALL provide a name/description search and a status filter (all / enabled / disabled / archived); a result count SHALL be shown. Each agent SHALL render as a card showing its name, status, and provenance, with quick actions; clicking a card SHALL open a detail drawer. Write controls SHALL be admin-only and hidden from viewers. A "New agent" control SHALL open a create modal that, in create mode, presents a required template `<select>` populated from `GET /admin/agent-templates`; selecting a template SHALL prefill the system prompt and allowed tools, and the create request SHALL include the chosen `template_id`. Saving a new agent without a selected template SHALL be blocked client-side.

#### Scenario: Admin sees the agent card grid and templates
- **WHEN** an admin opens the Agents tab
- **THEN** agents are listed as cards via `GET /admin/agents` and templates are available via `GET /admin/agent-templates`
- **AND** a search box and a status filter are present with a result count

#### Scenario: Card opens the detail drawer
- **WHEN** an admin clicks an agent card
- **THEN** a detail drawer opens showing the agent's metadata and binding-management sections

#### Scenario: Viewer cannot mutate agents
- **WHEN** a viewer opens the Agents tab
- **THEN** New-agent, edit, enable / disable / archive / restore / clone and all bind controls are hidden

#### Scenario: New-agent modal requires a template
- **WHEN** an admin opens the New-agent modal
- **THEN** a required template `<select>` populated from the templates endpoint is shown
- **AND** attempting to save without choosing a template is blocked
- **AND** choosing a template prefills the system prompt and allowed tools and sends `template_id` on create

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
The agent detail drawer SHALL let an admin manage the agent and every binding from one place. It SHALL provide: an **edit** action that reads `GET /admin/agents/{name}` to prefill and saves via `PATCH /admin/agents/{name}`; lifecycle actions (enable, disable, archive/restore, delete with reference protection, clone); a **Versions** section listing versions with an activate control (`POST /admin/agents/{name}/versions/{version}/activate`); and a "manage the bound list" section for each binding type below. Every binding section SHALL show the agent's currently bound items and offer add/remove. All write controls SHALL be hidden from viewers.

- **Skills**: load `GET /admin/agents/{name}/skills` and toggle per skill via `PUT /admin/agents/{name}/skills/{skill_name}`.
- **Connectors**: MCP servers — options from `GET /admin/mcp/servers`, current state from `GET /admin/agents/{name}/bindings`, toggled via `POST`/`DELETE /admin/agents/{name}/bindings/mcp/{server_id}`; OAuth connectors — options from `GET /admin/connectors`, current state and toggle via the agent OAuth binding endpoints.
- **Knowledge bases**: list the agent's bound KBs and bind/unbind via the agent knowledge-base binding endpoints.
- **IM**: list and bind/unbind users (`POST`/`DELETE /admin/agents/{name}/bindings/users/{user_id}`) and channels (`POST`/`DELETE /admin/agents/{name}/bindings/channels/{platform}/{channel}`), with each bound row offering an unbind control.

#### Scenario: Edit an agent from the drawer
- **WHEN** an admin opens an agent's edit action, changes a field, and saves
- **THEN** the console first reads `GET /admin/agents/{name}` to prefill, then calls `PATCH /admin/agents/{name}` and the change is reflected

#### Scenario: Activate a version
- **WHEN** an admin activates a listed version in the Versions section
- **THEN** the console calls `POST /admin/agents/{name}/versions/{version}/activate`

#### Scenario: Manage the bound skills list
- **WHEN** an admin toggles a skill in the Skills section
- **THEN** the console calls `PUT /admin/agents/{name}/skills/{skill_name}` and the bound-skills list reflects the change

#### Scenario: Manage the bound connectors list
- **WHEN** an admin binds or unbinds an MCP server or an OAuth connector
- **THEN** the console calls the matching MCP binding endpoint (`POST`/`DELETE /admin/agents/{name}/bindings/mcp/{server_id}`) or OAuth binding endpoint, and the bound-connectors list reflects the change

#### Scenario: Manage the bound knowledge-base list
- **WHEN** an admin binds or unbinds a knowledge base from the agent
- **THEN** the console calls the agent knowledge-base binding endpoints and the bound-KB list reflects the change

#### Scenario: Manage IM bindings
- **WHEN** an admin binds or unbinds a user or channel
- **THEN** the console calls the matching user/channel binding endpoint and the bound list reflects the change

#### Scenario: Viewer cannot mutate bindings
- **WHEN** a viewer opens an agent's detail drawer
- **THEN** all add/remove/toggle controls across every binding section are hidden

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
