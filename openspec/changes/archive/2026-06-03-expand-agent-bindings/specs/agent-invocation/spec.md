## ADDED Requirements

### Requirement: Agent invocation resolves live resource bindings

At the start of an agent invocation the runtime SHALL resolve the agent's live resource
bindings and apply them on top of the version snapshot: the skill index SHALL be
restricted to the agent's enabled `agent_skills` when any exist (else all skills in
`skills_dir`), and the MCP tool-schema filter SHALL use the union of the snapshot's
`mcp_server_ids` and the agent's `agent_mcp_servers` bindings. Binding resolution
SHALL apply identically on the non-streaming and streaming invocation paths.

#### Scenario: Skill binding restricts injection

- **WHEN** an invocation runs for an agent that has `agent_skills` rows
- **THEN** only enabled skills are eligible for injection in that invocation

#### Scenario: MCP binding widens tool schemas

- **WHEN** an invocation runs for an agent bound to MCP server "github"
- **THEN** "github" tools are present in the filtered tool schemas in addition to snapshot servers

#### Scenario: Streaming path matches non-streaming

- **WHEN** the same agent is invoked via the streaming path
- **THEN** the same resolved skill set and MCP server union are applied
