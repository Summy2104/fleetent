# permission-gate Delta

## MODIFIED Requirements

### Requirement: Async approval wait
The system SHALL NOT block agent execution while waiting for approval. Instead the gate
SHALL register the approval, send the prompt (interactive where supported), and return a
`pending` result immediately; the loop then suspends the run (see the
`approval-suspend-resume` capability) rather than awaiting an `asyncio.Event`. Resolution
arrives out-of-band (Slack button or `approve`/`reject <id>` text command) and drives
resume, not a coroutine wake-up.

#### Scenario: Approved
- **WHEN** user clicks "Allow" (or sends `approve <id>`) for a pending approval
- **THEN** the approval is resolved `approved` and the suspended run is resumed (the
  pending tool executes and the run continues), without relying on an in-process waiter

#### Scenario: Rejected
- **WHEN** user clicks "Deny" (or sends `reject <id>`) for a pending approval
- **THEN** the approval is resolved `rejected` and the suspended run resumes with a
  user-declined result, notifying the user the operation was cancelled

#### Scenario: request_approval does not block
- **WHEN** the gate's `request_approval` is invoked for a gated tool call
- **THEN** it registers the approval and returns `pending` without awaiting a decision

### Requirement: Approval timeout
The system SHALL reconcile approvals that exceed the configured timeout via the cleanup
routine rather than by waking a blocked coroutine. Because no coroutine is suspended on
the decision, timeout values MAY be configured generously; the defaults remain the
agent's `permission_gate_medium_timeout_seconds` / `permission_gate_high_timeout_seconds`
(300s / 3600s) where set.

#### Scenario: Expired approval reconciled by cleanup
- **WHEN** a pending approval exceeds its timeout
- **THEN** the cleanup routine marks the `approvals` row `timeout` and clears the
  session's `meta.pending_approvals` entry, leaving the session consistent

#### Scenario: Timeout values still configurable per agent
- **WHEN** an agent sets `permission_gate_medium_timeout_seconds` /
  `permission_gate_high_timeout_seconds`
- **THEN** those values bound the pending window used by the cleanup reconciliation
