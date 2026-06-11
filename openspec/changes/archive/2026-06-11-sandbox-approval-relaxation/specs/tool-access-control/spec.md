## MODIFIED Requirements

### Requirement: Empty allowed_tools SHALL permit all tools
When `allowed_tools` is an empty list in `agent.yaml`, the agent SHALL allow all registered tools EXCEPT tools designated **opt-in** (high-impact host-execution tools, currently `bash_exec`), consistent with the documented "empty = allow all" semantics for the non-opt-in surface. An opt-in tool SHALL be exposed to the LLM and dispatchable ONLY when `allowed_tools` explicitly names it — either as its literal tool name or via an explicit fnmatch pattern that covers it; an empty `allowed_tools` (allow-all) or a `["*"]` wildcard SHALL NOT implicitly grant any opt-in tool. The runtime SHALL still receive `allowed_tools=None` for an empty list (the opt-in exclusion is applied at the tool-surface layer, not by materializing a list), and the visibility of all non-opt-in tools under empty/`*` allow-all SHALL be unchanged. The opt-in designation MUST NOT alter the tool's own execution, approval, or timeout contract (that contract is owned by `builtin-shell-tool`).

#### Scenario: agent with allowed_tools empty list
- **WHEN** an agent is configured with `allowed_tools: []`
- **THEN** all registered non-opt-in tools (builtin + MCP) are exposed to the LLM and dispatchable
- **THEN** the runtime receives `allowed_tools=None` (not `[]`)
- **THEN** opt-in tools such as `bash_exec` are NOT exposed (the agent must name them explicitly to obtain them)

#### Scenario: agent with explicit tool patterns
- **WHEN** an agent is configured with `allowed_tools: ["run_code", "web_search"]`
- **THEN** only the listed tools are exposed to the LLM

#### Scenario: agent with wildcard pattern
- **WHEN** an agent is configured with `allowed_tools: ["*"]`
- **THEN** all non-opt-in tools are exposed (same behavior as empty list), and opt-in tools such as `bash_exec` are still NOT exposed (a bare `*` does not implicitly grant opt-in tools)

#### Scenario: ops agent explicitly opts into bash_exec
- **WHEN** an agent is configured with `allowed_tools` that explicitly names `bash_exec` (its literal name, or an explicit pattern that covers it)
- **THEN** `bash_exec` is exposed to the LLM and dispatchable for that agent, while its execution/approval/timeout contract remains unchanged
