## MODIFIED Requirements

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
