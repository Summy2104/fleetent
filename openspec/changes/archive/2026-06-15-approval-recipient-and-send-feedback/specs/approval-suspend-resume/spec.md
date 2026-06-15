## MODIFIED Requirements

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

Delivery receipts produced while executing the approved tool SHALL be surfaced in the
resumed run's final reply as the system-generated delivery fact trailer, so a successful
proactive send is confirmed deterministically to the originating conversation rather than
left to the model's discretion. The resume path SHALL share one delivery ledger between the
tool-execution context and the continuation run so the trailer rendered at the
continuation's finalize includes the receipts from the resumed tool execution.

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

#### Scenario: approved send is confirmed by a delivery trailer

- **WHEN** an approved `send_im_message` executes during resume and the message is delivered
- **THEN** the resumed run's final reply carries the system delivery fact trailer
  (`📬 实际投递：消息 …`) reflecting that send, independent of what the model wrote
