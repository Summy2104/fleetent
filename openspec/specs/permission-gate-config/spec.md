# permission-gate-config Specification

## Purpose
允许在 `agent.yaml` 中配置 permission gate 行为：通过 `permission_gate_enabled` 开关控制是否
对 medium/high risk 工具启用审批拦截，以及通过 `permission_gate_medium_timeout_seconds` /
`permission_gate_high_timeout_seconds` 控制审批超时时长。默认值保持向后兼容（enabled=true，
medium=300s，high=3600s）。

## Requirements

### Requirement: agent.yaml SHALL expose a permission_gate_enabled switch
`AgentFile` SHALL include a `permission_gate_enabled: bool` field (default `true`). When set to
`false`, the agent loop SHALL skip the approval gate entirely for all medium and high risk tools,
executing them immediately without waiting for user confirmation.

#### Scenario: gate disabled, medium-risk tool executes without approval
- **WHEN** `permission_gate_enabled: false` is set in `agent.yaml`
- **AND** the agent calls a tool with `risk_level="medium"` via Slack
- **THEN** the tool executes immediately without triggering an approval request

#### Scenario: gate disabled, high-risk tool executes without approval
- **WHEN** `permission_gate_enabled: false` is set in `agent.yaml`
- **AND** the agent calls a tool with `risk_level="high"` via Slack
- **THEN** the tool executes immediately without triggering an approval request

#### Scenario: gate enabled (default), medium-risk tool requires approval
- **WHEN** `permission_gate_enabled` is omitted or set to `true` in `agent.yaml`
- **AND** the agent calls a tool with `risk_level="medium"` via Slack
- **THEN** an approval request is sent to the user before execution (existing behavior)

### Requirement: agent.yaml SHALL wire permission_gate timeout fields to the gate
The `permission_gate_medium_timeout_seconds` and `permission_gate_high_timeout_seconds` fields
declared in `AgentFile` SHALL be read and applied to approval requests, overriding the module-level
defaults of 300s and 3600s respectively.

#### Scenario: custom medium timeout applied
- **WHEN** `permission_gate_medium_timeout_seconds: 60` is set in `agent.yaml`
- **AND** an approval for a medium-risk tool is requested but not resolved
- **THEN** the approval auto-rejects after 60 seconds

#### Scenario: custom high timeout applied
- **WHEN** `permission_gate_high_timeout_seconds: 600` is set in `agent.yaml`
- **AND** an approval for a high-risk tool is requested but not resolved
- **THEN** the approval auto-rejects after 600 seconds

#### Scenario: default timeout unchanged when not configured
- **WHEN** `permission_gate_medium_timeout_seconds` and `permission_gate_high_timeout_seconds`
  are omitted from `agent.yaml`
- **THEN** medium approval timeout defaults to 300 seconds and high to 3600 seconds
