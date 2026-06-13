# approval-suspend-resume Specification

## Purpose
审批挂起-恢复：gated 工具调用不阻塞 run，而是写 placeholder 占位结果挂起、以 awaiting_approval 结束并持久化 pending；人工决定（按钮/文本命令，含重启后）触发恢复——执行/拒绝该工具并续跑到最终回复。
## Requirements
### Requirement: Run suspends on a pending approval instead of blocking

When a tool call requires approval, the run SHALL NOT block waiting for the human
decision. Instead the gate registers the approval and sends the prompt, and the loop
SHALL write a placeholder tool result `awaiting_human_approval (id=<approval_id>)` for
that tool call's id — keeping the message history protocol-valid (no dangling
tool_call) — and end the run with `StopReason.awaiting_approval`. The pending mapping
`{approval_id → tool_call_id, tool_name, tool_args, risk, approver identity}` SHALL be
persisted to the session file `meta.pending_approvals` (agent-side; never a platform
table).

#### Scenario: medium tool call suspends the run

- **WHEN** the LLM proposes a medium-risk tool call and the permission gate is enabled
- **THEN** a placeholder `awaiting_human_approval` result is written for that tool_call_id,
  the run ends with `StopReason.awaiting_approval`, and `meta.pending_approvals` records
  the approval

#### Scenario: history stays valid after suspension

- **WHEN** a run has suspended on a pending approval
- **THEN** the persisted message history contains the assistant tool_calls message
  followed by the placeholder tool result, forming a valid sequence the next LLM call
  can consume

#### Scenario: non-gated tools in the same batch still execute

- **WHEN** a batch contains both a gated tool and a non-gated tool
- **THEN** the non-gated tool executes normally and only the gated tool gets the
  placeholder + suspension

### Requirement: Approval resolution resumes the run

The system SHALL resume the suspended run when a pending approval is resolved (via Slack
button or `approve`/`reject <id>` text command): on **approve**, it executes the pending
tool through the normal dispatch path (so tool_context / connectors are injected) and
appends the real result as a context message, then continues the run to a final reply; on
**reject**, it appends a user-declined context message and continues. The resolved pending
entry MUST be removed from `meta.pending_approvals`.

#### Scenario: approve executes the tool and continues

- **WHEN** an authorized actor approves a pending approval
- **THEN** the pending tool is executed, its result is injected as context, the run
  continues to a final reply, and the pending entry is cleared

#### Scenario: reject continues without executing

- **WHEN** an authorized actor rejects a pending approval
- **THEN** the tool is not executed, a "user declined" context is injected, the run
  continues to a final reply, and the pending entry is cleared

#### Scenario: text command and button resume identically

- **WHEN** the resolution arrives as a `approve <id>` text command OR a Slack button click
- **THEN** the same resume path runs (execute-or-decline → inject → continue)

### Requirement: Pending approvals survive a process restart

Resolution SHALL NOT depend on an in-memory `asyncio.Event`. With the pending mapping in
the session file and the approval row in the `approval_requests` table (subject_type=`tool_call`),
a decision made after a process restart SHALL still resume the run. The authorized decision
actors SHALL be recoverable after restart (persisted alongside the pending entry).

#### Scenario: approve after restart still resumes

- **WHEN** a process restart occurs while an approval is pending, then an authorized actor approves
- **THEN** the run resumes from the persisted `approval_requests` row + session `meta.pending_approvals`, without relying on any in-memory event

### Requirement: Same-session messages during a pending approval are processed

While an approval is pending, a new ordinary message in the same session SHALL be
processed as a normal turn (the history is already valid), not swallowed as steering
input. The run SHALL surface the outstanding pending approval to the model as context so
it does not silently re-propose the same gated call.

#### Scenario: new message is not swallowed as steering

- **WHEN** an approval is pending and the user sends an unrelated message in the same session
- **THEN** the message starts a normal turn and receives its own reply (not
  `📝 已把你的补充发给正在进行的任务`)

#### Scenario: model is aware of the outstanding approval

- **WHEN** a turn runs while `meta.pending_approvals` is non-empty
- **THEN** the run injects a context note about the outstanding approval so the model
  does not re-issue the same gated tool call

### Requirement: Expired approvals are reconciled

A pending approval that exceeds its timeout SHALL be reconciled by the cleanup routine:
the `approval_requests` row marked `expired` and the `meta.pending_approvals` entry removed, so
the session is left consistent. Because no coroutine is suspended, the approval window
MAY be configured generously.

#### Scenario: cleanup reconciles an expired pending approval

- **WHEN** the cleanup routine runs and finds a pending approval past its timeout
- **THEN** the `approval_requests` row is marked `expired` and the matching `meta.pending_approvals` entry is removed

