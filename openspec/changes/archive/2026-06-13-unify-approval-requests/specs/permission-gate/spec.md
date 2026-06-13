# permission-gate Delta

## MODIFIED Requirements

### Requirement: Approval persistence
All approval requests and outcomes SHALL be recorded in the `approval_requests` table (subject_type=`tool_call`), the unified approval-lifecycle source of truth — no longer in a separate `approvals` table. The tool-call resume context (the suspended call) remains in the session's `meta.pending_approvals`.

#### Scenario: Approval record lifecycle
- **WHEN** a permission gate triggers
- **THEN** an `approval_requests` row is inserted with `subject_type=tool_call` and `status=pending`, and updated to `approved`/`rejected`/`expired` when resolved
