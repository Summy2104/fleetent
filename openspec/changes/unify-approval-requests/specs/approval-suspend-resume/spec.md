# approval-suspend-resume Delta

## MODIFIED Requirements

### Requirement: Pending approvals survive a process restart

Resolution SHALL NOT depend on an in-memory `asyncio.Event`. With the pending mapping in
the session file and the approval row in the `approval_requests` table (subject_type=`tool_call`),
a decision made after a process restart SHALL still resume the run. The authorized decision
actors SHALL be recoverable after restart (persisted alongside the pending entry).

#### Scenario: approve after restart still resumes

- **WHEN** a process restart occurs while an approval is pending, then an authorized actor approves
- **THEN** the run resumes from the persisted `approval_requests` row + session `meta.pending_approvals`, without relying on any in-memory event

### Requirement: Expired approvals are reconciled

A pending approval that exceeds its timeout SHALL be reconciled by the cleanup routine:
the `approval_requests` row marked `expired` and the `meta.pending_approvals` entry removed, so
the session is left consistent. Because no coroutine is suspended, the approval window
MAY be configured generously.

#### Scenario: cleanup reconciles an expired pending approval

- **WHEN** the cleanup routine runs and finds a pending approval past its timeout
- **THEN** the `approval_requests` row is marked `expired` and the matching `meta.pending_approvals` entry is removed
