# agent-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Agents management tab
The admin console SHALL present an Agents tab as a card grid (consistent with the Skills and Connectors modules), not a table. A toolbar SHALL provide a name/description search and a status filter (all / enabled / disabled / archived); a result count SHALL be shown. Each agent SHALL render as a card showing its name and status, with quick actions; clicking a card SHALL open a detail drawer. Write controls SHALL be admin-only and hidden from viewers. A "New agent" control SHALL open a create modal that, in create mode, presents a required template `<select>` populated from `GET /admin/agent-templates`; selecting a template SHALL prefill the system prompt and allowed tools, and the create request SHALL include the chosen `template_id`. Saving a new agent without a selected template SHALL be blocked client-side.

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
The console SHALL let an admin enable, disable, archive, restore, and clone an agent, and view observability, calling the matching endpoints. The per-row agent actions SHALL be collapsed into a single `⋯` overflow menu rather than rendered as a flat button row; admin-only items SHALL remain hidden for viewers. （Deploy-to-channel 动作随 `channel_agents` 与渠道绑定端点 descope 移除。）

#### Scenario: Clone an agent
- **WHEN** an admin clones an agent
- **THEN** the console calls `POST /admin/agents/{name}/clone` and the new agent appears

#### Scenario: Row actions live in an overflow menu
- **WHEN** an admin views the agents list
- **THEN** each row's actions are reached through a `⋯` overflow menu (not a flat row of buttons)
- **AND** the menu contains the existing actions (stats, edit, bindings, clone, enable/disable, archive/restore, delete)
- **AND** viewer sessions still hide the admin-only items

### Requirement: Agent bindings and native configuration
The agent detail view in the React SPA SHALL let an admin manage the agent and every binding **natively from one place (not deep-linked to the legacy console)**. It SHALL provide: an **edit** action that reads `GET /admin/agents/{name}` to prefill and saves via `PATCH /admin/agents/{name}`; lifecycle actions (enable, disable, archive/restore, delete with reference protection, clone); and a "manage the bound list" section for each binding type below. Every binding section SHALL show the agent's currently bound items and offer add/remove. The deploy section SHALL expose deploy/yaml export only; it SHALL NOT render version history or activation controls. All write controls SHALL be hidden from viewers.

- **Skills**: load `GET /admin/agents/{name}/skills` and toggle per skill via `PUT /admin/agents/{name}/skills/{skill_name}`.
- **Connectors**: MCP servers — options from `GET /admin/mcp/servers`, current state from `GET /admin/agents/{name}/bindings`, toggled via `POST`/`DELETE /admin/agents/{name}/bindings/mcp/{server_id}`; OAuth connectors — options from `GET /admin/connectors`, current state from `GET /admin/agents/{name}/bindings/oauth`, toggled via `POST`/`DELETE /admin/agents/{name}/bindings/oauth/{connector_id}`.
- **Knowledge bases**: list via `GET /admin/agents/{name}/kbs` and bind/unbind via `POST`/`DELETE /admin/agents/{name}/kbs/{kb_id}`.
- **User access**: list via `GET /admin/agents/{name}/bindings` and bind/unbind via `POST`/`DELETE /admin/agents/{name}/bindings/users/{user_id}`.
- **IM access**: manage the per-platform group whitelist via `POST /admin/agents/{name}/bindings/groups`, and toggle DM / group capabilities via `PUT /admin/agents/{name}/im-capabilities`.
- **Default agent**: mark/unmark this agent as the tenant default via `PUT /admin/agents/{name}/default` / `DELETE /admin/agents/default`.
- **Secrets**: list env-var slots via `GET /admin/agents/{name}/secrets` and set/clear a value via `PUT`/`DELETE /admin/agents/{name}/secrets/{env_name}`. A secret value SHALL be write-only — never displayed in plaintext.

#### Scenario: Edit an agent from the detail view
- **WHEN** an admin opens an agent's edit action, changes a field, and saves
- **THEN** the SPA first reads `GET /admin/agents/{name}` to prefill, then calls `PATCH /admin/agents/{name}` and the change is reflected

#### Scenario: Manage bound skills / connectors / KBs / users natively
- **WHEN** an admin toggles a skill, binds/unbinds an MCP server or OAuth connector, binds/unbinds a knowledge base, or binds/unbinds a user
- **THEN** the SPA calls the matching agent binding endpoint natively (no legacy deep-link) and the relevant bound list reflects the change

#### Scenario: Manage IM access
- **WHEN** an admin adds/removes an IM group from the agent's whitelist, or toggles DM / group capabilities
- **THEN** the SPA calls `POST /admin/agents/{name}/bindings/groups` (resp. `PUT /admin/agents/{name}/im-capabilities`) and the state reflects the change

#### Scenario: Set or clear the default agent
- **WHEN** an admin marks this agent as default, or clears the default
- **THEN** the SPA calls `PUT /admin/agents/{name}/default` (resp. `DELETE /admin/agents/default`)

#### Scenario: Manage secrets write-only
- **WHEN** an admin sets a secret value for an env slot, then re-opens the secrets section
- **THEN** the SPA calls `PUT /admin/agents/{name}/secrets/{env_name}`, and the value is never displayed in plaintext afterward (only the slot/status is shown)

#### Scenario: Bindings are not deep-linked to legacy
- **WHEN** an admin opens an agent's detail view
- **THEN** binding management is rendered natively in the SPA, with no "legacy entry point" deep-links for skills/connectors/KB/users

#### Scenario: Viewer cannot mutate bindings
- **WHEN** a viewer opens an agent's detail view
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

### Requirement: Agents tab surfaces desired and runtime state

The Agents tab SHALL display, for each agent, both its **desired state**（`status`：enabled / disabled / archived）and its **runtime state**（来自响应的 `runtime` 投影：`phase` running/stopped、`health`、所在 `node_id`）。当 `runtime` 为 `null`（node 未上报）时 SHALL 呈现一个明确的「未运行 / 无上报」态，而非留空或显示陈旧值。绑定信息（`placement`：所在 node 或未绑定）SHALL 一并可见。

#### Scenario: Card shows desired and runtime state
- **WHEN** an agent's list/detail response carries `status="enabled"` and `runtime={phase:"running", health, node_id}`
- **THEN** the card shows both the desired status and the runtime phase/health and the node it runs on

#### Scenario: No runtime report renders an explicit not-running state
- **WHEN** an agent's `runtime` is `null`
- **THEN** the card shows an explicit not-running / no-report indication (not a blank or stale value)

### Requirement: Enable control is gated on node binding

When an agent is `disabled` and not bound to a node (`placement` is `null`), the Agents tab SHALL render the「Enable」control as **disabled** and SHALL surface the reason（提示管理员需先把 agent pin 到某个 node 才能启用）。当 `placement` 非空时「Enable」SHALL 可操作。「Disable」控件 SHALL NOT 受此约束。

#### Scenario: Enable disabled with a hint when unbound
- **WHEN** an agent is `disabled` and its `placement` is `null`
- **THEN** the「Enable」control is disabled and a reason hint is shown (must be pinned to a node first)

#### Scenario: Enable actionable once bound
- **WHEN** an agent is `disabled` and its `placement` is non-null
- **THEN** the「Enable」control is actionable and triggers `POST /admin/agents/{name}/enable`
