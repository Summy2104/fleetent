# Tool Access Control

## Purpose

Defines how the agent runtime interprets and applies the `allowed_tools` configuration from `agent.yaml` to control which tools are exposed to the LLM.

## Requirements

### Requirement: Empty allowed_tools SHALL permit all tools
When `allowed_tools` is an empty list in `agent.yaml`, the agent SHALL allow all registered tools (equivalent to no filter), consistent with the documented "empty = allow all" semantics.

#### Scenario: agent with allowed_tools empty list
- **WHEN** an agent is configured with `allowed_tools: []`
- **THEN** all registered tools (builtin + MCP) are exposed to the LLM and dispatchable
- **THEN** the runtime receives `allowed_tools=None` (not `[]`)

#### Scenario: agent with explicit tool patterns
- **WHEN** an agent is configured with `allowed_tools: ["run_code", "web_search"]`
- **THEN** only the listed tools are exposed to the LLM

#### Scenario: agent with wildcard pattern
- **WHEN** an agent is configured with `allowed_tools: ["*"]`
- **THEN** all tools are exposed (same behavior as empty list)
