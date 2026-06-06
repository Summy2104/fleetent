## ADDED Requirements

### Requirement: Capability-gated resource and prompt tools

For an MCP server whose advertised capabilities include `resources`, the client SHALL register synthetic tools to list and read that server's resources. For a server whose capabilities include `prompts`, the client SHALL register synthetic tools to list and get that server's prompts. A server that does not advertise a capability SHALL NOT get the corresponding tools. The synthetic tools SHALL use the `{server_id}__{name}` namespace like other MCP tools.

#### Scenario: Resource tools registered when advertised
- **WHEN** a server's captured capabilities include `resources`
- **THEN** tools `{server}__list_resources` and `{server}__read_resource` are registered

#### Scenario: Prompt tools registered when advertised
- **WHEN** a server's captured capabilities include `prompts`
- **THEN** tools `{server}__list_prompts` and `{server}__get_prompt` are registered

#### Scenario: No tools for unadvertised capability
- **WHEN** a server's captured capabilities include neither `resources` nor `prompts`
- **THEN** no resource or prompt synthetic tools are registered for it

### Requirement: Synthetic tools dispatch to MCP methods

Invoking a resource/prompt synthetic tool SHALL dispatch to the corresponding MCP method on that server (over the server's transport) and return the result as text. `read_resource` SHALL pass the caller's `uri`; `get_prompt` SHALL pass the caller's `name` and optional `arguments`.

#### Scenario: read_resource forwards the uri
- **WHEN** the `{server}__read_resource` tool is invoked with a `uri`
- **THEN** the client issues a resources/read for that uri and returns its result as text

#### Scenario: list returns server data as text
- **WHEN** the `{server}__list_resources` tool is invoked
- **THEN** the client returns the server's resource listing serialized as text

### Requirement: Synthetic tools follow availability and refresh rules

The resource/prompt synthetic tools SHALL be subject to the same availability handling as other MCP tools of the server: when the server is unavailable they SHALL return the unavailable result rather than calling out. After a stdio tools refresh (list_changed), the still-advertised resource/prompt tools SHALL remain registered.

#### Scenario: Unavailable server short-circuits
- **WHEN** a resource/prompt synthetic tool is invoked for a server whose connection is not healthy
- **THEN** it returns the temporarily-unavailable result without making a request

#### Scenario: Refresh preserves utility tools
- **WHEN** a stdio server that advertises `resources` undergoes a tools/list_changed refresh
- **THEN** its `{server}__list_resources` and `{server}__read_resource` tools are still registered afterward
