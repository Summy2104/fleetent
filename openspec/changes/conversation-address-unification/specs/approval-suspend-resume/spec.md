# approval-suspend-resume Delta

## MODIFIED Requirements

### Requirement: Run suspends on a pending approval instead of blocking

When a tool call requires approval, the run SHALL NOT block waiting for the human
decision. Instead the gate registers the approval and sends the prompt, and the loop
SHALL write a placeholder tool result `awaiting_human_approval (id=<approval_id>)` for
that tool call's id — keeping the message history protocol-valid (no dangling
tool_call) — and end the run with `StopReason.awaiting_approval`. The pending mapping
`{approval_id → tool_call_id, tool_name, tool_args, risk, approver identity, address}`
SHALL be persisted to the session file `meta.pending_approvals` (agent-side; never a
platform table), where `address` is the run's `ConversationAddress` (platform, chat_id,
target_type, thread_id, user_id) plus the SessionContext routing fields (chat_type,
thread_root) needed to rebuild an equivalent delivery context at resume time.

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

#### Scenario: pending entry carries the conversation address

- **WHEN** a run suspended from inside a Slack thread persists its pending entry
- **THEN** the entry's `address` records the originating platform, chat, thread and user

### Requirement: Approval resolution resumes the run

The system SHALL resume the suspended run when a pending approval is resolved (via Slack
button or `approve`/`reject <id>` text command): on **approve**, it executes the pending
tool through the normal dispatch path (so tool_context / connectors are injected) and
appends the real result as a context message, then continues the run to a final reply; on
**reject**, it appends a user-declined context message and continues. The resumed run's
delivery context (reply_func, upload_func, progress, SessionContext) SHALL be rebuilt
from the pending entry's persisted `address` via the outbound factories — NOT from the
context of the message or click that triggered the resolution — so resumed output lands
in the original chat/thread with upload capability intact. The resolved pending entry
MUST be removed from `meta.pending_approvals`.

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
- **THEN** the same resume path runs (execute-or-decline → inject → continue) and the
  resumed output lands at the same persisted address regardless of entry point

#### Scenario: resumed output returns to the original thread

- **WHEN** a run suspended inside a Slack thread is resolved from anywhere (button click
  or a top-level `approve <id>` message)
- **THEN** the resumed run's replies and any subsequent approval prompts are posted into
  the original thread recorded in the pending entry's address
