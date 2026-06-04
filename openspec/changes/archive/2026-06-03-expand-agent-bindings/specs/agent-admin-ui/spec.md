## MODIFIED Requirements

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
