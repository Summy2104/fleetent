## ADDED Requirements

### Requirement: Declarative tool-name projection configuration
The agent runtime SHALL render every MCP tool's model-facing name through a configurable projection declared at `mcp.tool_naming` in `agent.yaml`. The value SHALL be either a preset alias (`claude`, `hermes`, `opencode`, `skills`, `bare`) or a custom object `{ template, sanitize, max_len }`, where `template` uses the `{server}` and `{tool}` placeholders. Presets SHALL be equivalent to built-in templates. When `mcp.tool_naming` is omitted, the projection SHALL default to `claude` (`mcp__{server}__{tool}`). Supporting a new platform's naming SHALL require only configuration (a template), not code changes.

#### Scenario: default projection
- **WHEN** `mcp.tool_naming` is unset AND server `github` exposes tool `create_issue`
- **THEN** the LLM-facing tool name is `mcp__github__create_issue`

#### Scenario: preset projection
- **WHEN** `mcp.tool_naming: hermes` AND server `github` exposes `create_issue`
- **THEN** the LLM-facing tool name is `mcp_github_create_issue`

#### Scenario: custom template projection
- **WHEN** `mcp.tool_naming: { template: "{server}:{tool}" }` AND server `github` exposes `create_issue`
- **THEN** the LLM-facing tool name is `github:create_issue`

#### Scenario: length cap applied
- **WHEN** a projected name would exceed `max_len` (default 64)
- **THEN** the projection deterministically shortens the name to satisfy the limit while keeping it unique

### Requirement: Canonical-internal projection at the LLM boundary
Projection SHALL occur ONLY at the LLM boundary: tool schemas SHALL be presented to the model under the projected name, and an inbound tool call referencing a projected name SHALL be resolved to its canonical identity before any downstream handling. The tool registry SHALL register MCP tools under their canonical identity; tool dispatch, observability, loop guardrails, and access control SHALL operate on the canonical identity, unchanged by the projection. Resolution SHALL use an agent-process-local reverse-lookup table built at registration, and SHALL NOT parse the projected name string.

#### Scenario: inbound projected name resolves to canonical dispatch
- **WHEN** `mcp.tool_naming: hermes` AND the LLM calls `mcp_github_create_issue`
- **THEN** dispatch routes to MCP server `github`, tool `create_issue`
- **AND** resolution uses the reverse-lookup table, not string splitting

#### Scenario: ambiguous single-underscore name resolves correctly
- **WHEN** `mcp.tool_naming: hermes` AND server `google_drive` exposes `list_files` (projected `mcp_google_drive_list_files`)
- **THEN** the call resolves to server `google_drive`, tool `list_files` via the reverse-lookup table

### Requirement: Governance binds the canonical identity
Governance (approval and access control) SHALL operate on the canonical identity, independent
of `mcp.tool_naming`. The LLM boundary SHALL resolve a projected tool name back to its
canonical name BEFORE governance runs, so risk classification and `allowed_tools` matching
never see — and never parse — a projected name. For any `mcp.tool_naming` value, an MCP tool
matched by an `approval_rules` entry SHALL still be gated, and `allowed_tools` matching SHALL
behave identically. The canonical `(server_id, raw_tool)` identity recorded at registration
is also exposed (``mcp_tool_identity``) for consumers that need the structured pair.

#### Scenario: approval still triggers under any naming
- **WHEN** an `approval_rules` entry requires approval for server `crm` tool `create_contact` AND `mcp.tool_naming` is `claude`, `hermes`, or `bare`
- **THEN** a call to that tool (under whatever projected name) is classified medium and routed to the approval gate

#### Scenario: read-only tool not over-gated under any naming
- **WHEN** server `crm` tool `get_contact` has no matching approval rule
- **THEN** the call is not gated, regardless of `mcp.tool_naming`

### Requirement: Agent-side and decoupled projection
The projection engine and reverse-lookup table SHALL live entirely in the agent runtime (`fleetent.integrations.mcp`) and SHALL NOT depend on the platform. A standalone agent (`fleetent agent run`) SHALL build the projection solely from `agent.yaml` (`mcp.tool_naming`) without any platform or database.

#### Scenario: standalone agent projects without platform
- **WHEN** `fleetent agent run` starts with `mcp.tool_naming: claude` and an MCP server configured in `agent.yaml`
- **THEN** MCP tools are exposed as `mcp__{server}__{tool}` with no platform or database involved
