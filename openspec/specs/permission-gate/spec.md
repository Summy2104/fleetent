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

Tools SHALL declare their risk level at registration time via `@tool(risk_level=...)`, as either a string constant (`"none"`/`"low"`/`"medium"`/`"high"`, existing semantics unchanged) or a callable `(tool_args, tool_context) -> "low" | "medium" | "high"` evaluated at dispatch time. A callable MUST be a pure function of its inputs (no I/O side effects beyond reads), MUST be evaluated once per call before the action-mode decision, and its returned level MUST drive the same gate behavior as the equivalent string constant. If the callable raises, the gate MUST fail closed by treating the call as `"medium"`.

#### Scenario: Tool with no risk

- **WHEN** a tool is registered with `risk_level="none"` (or no risk_level specified)
- **THEN** it executes immediately after access control passes

#### Scenario: Tool with medium risk

- **WHEN** a tool is registered with `risk_level="medium"`
- **THEN** a confirmation request is sent to the requester via IM DM before execution

#### Scenario: Tool with high risk

- **WHEN** a tool is registered with `risk_level="high"`
- **THEN** an approval request is sent to the pre-configured approver, and the requester is notified "waiting for admin approval"

#### Scenario: Callable risk evaluates low

- **WHEN** a tool registered with a callable risk_level is dispatched and the callable returns `"low"` for the given args and context
- **THEN** the tool executes without an approval prompt

#### Scenario: Callable risk evaluates medium

- **WHEN** the same tool is dispatched with args for which the callable returns `"medium"`
- **THEN** the call passes the medium approval flow identical to a static `risk_level="medium"` tool

#### Scenario: Callable failure fails closed

- **WHEN** the risk callable raises an exception during evaluation
- **THEN** the call is treated as `"medium"` (approval required), never as free

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

### Requirement: Approval persistence
All approval requests and outcomes SHALL be recorded in the `approval_requests` table (subject_type=`tool_call`), the unified approval-lifecycle source of truth — no longer in a separate `approvals` table. The tool-call resume context (the suspended call) remains in the session's `meta.pending_approvals`.

#### Scenario: Approval record lifecycle
- **WHEN** a permission gate triggers
- **THEN** an `approval_requests` row is inserted with `subject_type=tool_call` and `status=pending`, and updated to `approved`/`rejected`/`expired` when resolved

### Requirement: permission gate SHALL be skippable per agent
The loop's `_plan_run_slots` function SHALL accept a `permission_gate_enabled` flag. When `False`,
medium and high risk tool calls SHALL bypass the approval gate and proceed directly to execution.

#### Scenario: gate disabled at loop level
- **WHEN** `loop.run()` is called with `permission_gate_enabled=False`
- **AND** a tool with `risk_level="medium"` or `risk_level="high"` is planned
- **THEN** no approval request is made and the tool proceeds to execution immediately

### Requirement: Requester sentinel approval routing

The approval routing configuration SHALL accept the sentinel value `requester` in any
`approvers` list (alongside `platform:target_id` addresses). When resolved for a pending
approval, the gate SHALL deliver the approval prompt back to the current conversation via
the run's `reply_func` (including the approval id and the `approve <id>` / `reject <id>`
instructions) instead of contacting an outbound address. Sentinel and outbound addresses
MAY be mixed in one list; the first decision from any authorized actor wins.

#### Scenario: requester sentinel routes the prompt to the current conversation

- **WHEN** `approval_routing` resolves to `approvers: ["requester"]` for a pending tool call
- **THEN** the approval prompt is sent via `reply_func` to the current conversation and no
  outbound DM is attempted

#### Scenario: requester decides in-conversation

- **WHEN** the requesting user replies `approve <id>` in the same conversation
- **THEN** the gate resolves the approval and the tool call proceeds

#### Scenario: mixed list notifies both channels

- **WHEN** `approvers: ["requester", "slack:U_ADMIN"]` resolves for a pending tool call
- **THEN** the prompt is sent via `reply_func` AND the outbound approver is contacted, and
  the first decision from either authorized actor resolves the request

#### Scenario: unconfigured deployments are unaffected

- **WHEN** no `requester` sentinel appears in any `approvers` list
- **THEN** routing behavior is identical to the pre-change implementation (outbound only,
  default-closed when no approver is reachable)

### Requirement: Approval decision authorization

The gate SHALL record, per pending approval, the set of authorized decision actors:
the requester's user id when the `requester` sentinel routed the prompt, and the target
ids of outbound approvers actually reached. `resolve()` SHALL reject a decision whose
`approver_user_id` is not in the pending approval's authorized set — returning False,
leaving the approval pending, and logging a warning.

#### Scenario: bystander in a channel cannot decide

- **WHEN** an approval prompt was routed to the requester in a channel and a different
  user replies `approve <id>`
- **THEN** `resolve()` returns False, the approval stays pending, and a warning is logged

#### Scenario: notified outbound approver can decide

- **WHEN** an outbound approver who was actually contacted replies `approve <id>`
- **THEN** `resolve()` accepts the decision and execution proceeds

#### Scenario: un-notified address cannot decide

- **WHEN** a user whose address appears in configuration but was NOT reached during
  notification replies `reject <id>`
- **THEN** `resolve()` returns False and the approval stays pending

### Requirement: Approval prompts carry interactive actions where supported

Approval prompts SHALL include platform-rendered interactive actions (approve / reject /
approve-always) on delivery channels that support them, while always retaining the
text-command instructions as a universal fallback. The gate SHALL pass the interactive
payload opaquely (it does not know platform rendering details) and SHALL degrade to the
plain-text prompt when the delivery channel rejects the payload. The gate MUST NOT import
or construct any platform-specific rendering (e.g. Slack Block Kit); rendering SHALL happen
at the outbound delivery boundary, dispatched by platform (Slack → Block Kit; Telegram →
inline keyboard), so that adding a delivery platform never changes the gate. Telegram SHALL
be a supporting channel: its approval prompts carry an inline keyboard whose buttons encode
the `approval_id` and the decision.

Approval prompts SHALL additionally carry a human-readable summary of the gated call so the
approver can verify WHAT is being approved before deciding — in both the interactive payload
and the text fallback. For `send_im_message` the summary SHALL identify the recipient,
resolving the platform-native target id to a display label best-effort via the injected IM
connector (Slack `users.info` → `@<name>`, `conversations.info` → `#<name>`), falling back to
the raw id on any failure or timeout so the prompt is never blocked or delayed; it SHALL also
state the target type (DM vs channel), a short preview of the message text, and the attachment
count when files are attached. For other gated tools the summary SHALL be a compact,
secret-masked rendering of the call arguments. Summary construction MUST NOT raise and MUST
NOT depend on `fleetent.platform`.

#### Scenario: requester prompt carries actions on a supporting channel

- **WHEN** a requester-routed approval prompt is delivered through a reply channel that
  accepts an interactive payload
- **THEN** the prompt message includes the interactive actions alongside the text
  instructions

#### Scenario: outbound approver DM carries actions

- **WHEN** an outbound approver is contacted on a platform supporting interactive
  payloads
- **THEN** the approver DM includes the interactive actions alongside the text instructions

#### Scenario: gate passes a neutral intent rendered at the boundary

- **WHEN** the gate builds an approval prompt
- **THEN** it produces a platform-neutral interactive intent (approval id + action set +
  summary) without importing or constructing Slack Block Kit, and the outbound boundary
  renders it per platform (Slack Block Kit unchanged; Telegram inline keyboard)

#### Scenario: Telegram approval prompt carries an inline keyboard

- **WHEN** an approval prompt is delivered to a Telegram approver
- **THEN** the message carries an inline keyboard with approve / reject / approve-always
  buttons whose callback data encodes the approval id and decision, alongside the text
  fallback

#### Scenario: send_im_message prompt shows the resolved recipient

- **WHEN** a `send_im_message(target="U_OTHER", text="...", target_type="user")` call is gated
  and the approval prompt is built with a reachable Slack connector
- **THEN** the prompt (interactive and text) shows the recipient resolved to a display label
  (e.g. `@张三`), the target type (私信), and a preview of the message text

#### Scenario: recipient resolution failure degrades to raw id

- **WHEN** the recipient display name cannot be resolved (API error/timeout or non-Slack platform)
- **THEN** the prompt shows the raw target id instead, and the prompt is still delivered
  (resolution failure never blocks or delays the approval prompt)

