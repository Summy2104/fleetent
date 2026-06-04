# permission-gate Specification

## Purpose
人在回路（human-in-the-loop）的工具审批门。被标注 `risk_level` 的工具在执行前暂停，先经访问控制（`allowed_tools` 白名单）校验，再按风险等级触发审批：medium 向请求者本人发确认、high 向预配置审批人发审批。审批通过 `asyncio.Event` 阻塞 agent 执行，等待 IM 回调放行/拒绝或超时自动拒绝；全过程的请求与结果落 `approvals` 表，留可审计的轨迹并跨重启存活。

## Requirements

### Requirement: Access control at dispatch
The system SHALL check `agent.allowed_tools` before executing any tool, as the first gate in `tool_registry.dispatch()`.

#### Scenario: Tool not in allowed_tools
- **WHEN** agent calls a tool not listed in its `allowed_tools`
- **THEN** `tool_registry.dispatch` raises `PermissionError` immediately, before any risk-level check

#### Scenario: Tool in allowed_tools
- **WHEN** agent calls a tool listed in its `allowed_tools`
- **THEN** dispatch proceeds to risk-level evaluation

### Requirement: Risk-level declaration
Tools SHALL declare their risk level at registration time via `@tool(risk_level=...)`.

#### Scenario: Tool with no risk
- **WHEN** a tool is registered with `risk_level="none"` (or no risk_level specified)
- **THEN** it executes immediately after access control passes

#### Scenario: Tool with medium risk
- **WHEN** a tool is registered with `risk_level="medium"`
- **THEN** a confirmation request is sent to the requester via IM DM before execution

#### Scenario: Tool with high risk
- **WHEN** a tool is registered with `risk_level="high"`
- **THEN** an approval request is sent to the pre-configured approver, and the requester is notified "waiting for admin approval"

### Requirement: Async approval wait
The system SHALL block agent execution using `asyncio.Event` while waiting for approval.

#### Scenario: Approved
- **WHEN** user clicks "Allow" in the IM approval message
- **THEN** the IM callback resolves the approval (`status=approved`), calls `event.set()`, and agent execution continues

#### Scenario: Rejected
- **WHEN** user clicks "Deny" in the IM approval message
- **THEN** the callback resolves (`status=rejected`), calls `event.set()`, and agent notifies the user "operation cancelled"

### Requirement: Approval timeout
The system SHALL auto-reject approvals that exceed the configured timeout.

#### Scenario: Medium risk timeout
- **WHEN** no response is received within `permission_gate.medium_timeout_seconds` (default 300)
- **THEN** approval is auto-rejected, `approvals` table updated to `status=timeout`, user notified

#### Scenario: High risk timeout
- **WHEN** no response is received within `permission_gate.high_timeout_seconds` (default 3600)
- **THEN** same auto-reject behavior

### Requirement: Approval persistence
All approval requests and outcomes SHALL be recorded in the `approvals` table.

#### Scenario: Approval record lifecycle
- **WHEN** a permission gate triggers
- **THEN** a row is inserted with `status=pending`, and updated to `approved`/`rejected`/`timeout` when resolved
