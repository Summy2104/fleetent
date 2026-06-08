## MODIFIED Requirements

### Requirement: Approval timeout
The system SHALL auto-reject approvals that exceed the configured timeout. Timeout values
SHALL be read from the agent's `permission_gate_medium_timeout_seconds` and
`permission_gate_high_timeout_seconds` fields when available, falling back to module defaults
(300s medium, 3600s high) when called outside an agent context.

#### Scenario: Medium risk timeout
- **WHEN** no response is received within the agent's configured `permission_gate_medium_timeout_seconds` (default 300)
- **THEN** approval is auto-rejected, `approvals` table updated to `status=timeout`, user notified

#### Scenario: High risk timeout
- **WHEN** no response is received within the agent's configured `permission_gate_high_timeout_seconds` (default 3600)
- **THEN** same auto-reject behavior

## ADDED Requirements

### Requirement: permission gate SHALL be skippable per agent
The loop's `_plan_tool_slots` function SHALL accept a `permission_gate_enabled` flag. When `False`,
medium and high risk tool calls SHALL bypass the approval gate and proceed directly to execution.

#### Scenario: gate disabled at loop level
- **WHEN** `loop.run()` is called with `permission_gate_enabled=False`
- **AND** a tool with `risk_level="medium"` or `risk_level="high"` is planned
- **THEN** no approval request is made and the tool proceeds to execution immediately
