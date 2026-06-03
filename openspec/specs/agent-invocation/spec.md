# agent-invocation Specification

## Purpose
TBD - created by archiving change 2026-05-29-multi-agent-management. Update Purpose after archive.
## Requirements
### Requirement: invoke_agent built-in tool
A built-in tool `invoke_agent(agent_name: str, message: str) -> str` SHALL allow a parent agent to dispatch a message to another registered agent and receive its reply. The tool SHALL be registered with `risk_level="medium"`.

#### Scenario: Successful invocation
- **WHEN** the parent agent calls `invoke_agent(agent_name="analyst", message="summarize Q4")`
- **AND** human approval is granted
- **THEN** the target agent runs with the snapshot of `analyst`'s active version and returns its final reply as the tool result

#### Scenario: Unknown agent
- **WHEN** `invoke_agent` is called with a name that does not exist (or is soft-deleted)
- **THEN** the tool returns a string `agent {name!r} not found` without raising

#### Scenario: Invocation requires approval
- **WHEN** `invoke_agent` is called and `reply_func` is set
- **THEN** the permission gate is engaged with `risk_level="medium"` before the target agent runs

### Requirement: Depth limit of 1 enforced via is_sub_agent
The target agent invoked via `invoke_agent` SHALL run with `is_sub_agent=True`, which excludes both `sub_agent` and `invoke_agent` from its visible tool schema.

#### Scenario: Nested invocation blocked
- **WHEN** an agent invoked through `invoke_agent` attempts to call `invoke_agent` or `sub_agent` itself
- **THEN** neither tool is exposed to it; the LLM cannot select either

#### Scenario: Reply still uses target snapshot's resources
- **WHEN** an `invoke_agent` call resolves and the target agent runs
- **THEN** the target's `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace` apply (not the parent's)

### Requirement: invoke_agent does not bypass parent's permission model
The `invoke_agent` tool call itself SHALL respect the parent agent's `allowed_tools` allowlist. If `invoke_agent` is not present in the parent's allowed_tools, it MUST be filtered out of the schema.

#### Scenario: Parent without invoke_agent in allowlist
- **WHEN** parent agent's `allowed_tools = ["shell"]`
- **THEN** `invoke_agent` is not in the schema offered to the parent and cannot be called

### Requirement: invoke_agent runs are recorded in eval trace under their own agent_name
Each invocation triggered by `invoke_agent` SHALL produce a separate eval-trace entry tagged with the target agent's name, distinct from the parent's trace.

#### Scenario: Trace lineage
- **WHEN** parent agent `coordinator` calls `invoke_agent(agent_name="analyst", message=...)` and `analyst` completes
- **THEN** the eval trace contains a row with `agent_name="analyst"` covering the invoked run, in addition to the parent's `agent_name="coordinator"` row for the outer run

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

