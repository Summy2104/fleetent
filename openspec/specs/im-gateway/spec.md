## Purpose

Receive messages from IM platforms (Slack, Telegram) via their SDKs, normalize them
into a uniform `NormalizedMessage` contract, and route them through the agent pipeline
with thread-first replies and automatic SDK reconnect.
## Requirements
### Requirement: Normalize Slack messages
The system SHALL receive Slack events via Socket Mode and normalize them into a `NormalizedMessage` before routing to the agent pipeline. Session id SHALL be derived **thread-first**: the bot replies inside the thread rooted at the user's message (`thread_root = thread_ts or the message's own ts`), and the session id is keyed by that thread root — `slack:dm:{user_id}:{thread_root}` for DMs and `slack:thread:{channel_id}:{thread_root}` for channels. A top-level message and its follow-ups inside the bot-created thread therefore share one session; each new top-level message (or new assistant-pane conversation) starts a new session.

#### Scenario: Slack DM top-level message
- **WHEN** a Slack DM top-level message arrives from user `U123` with ts `100.1`
- **THEN** the bot replies within a thread rooted at `100.1`
- **AND** the adapter derives `session_id="slack:dm:U123:100.1"`

#### Scenario: Slack DM follow-up in the bot-created thread
- **WHEN** user `U123` replies inside that thread (`thread_ts="100.1"`)
- **THEN** the adapter derives the same `session_id="slack:dm:U123:100.1"` (conversation stays continuous)

#### Scenario: Slack assistant-pane new conversation
- **WHEN** a new assistant-pane conversation starts with assistant `thread_ts="200.2"` for user `U123`
- **THEN** the adapter derives `session_id="slack:dm:U123:200.2"` (a new session distinct from prior conversations)

#### Scenario: Slack channel @mention starts a thread
- **WHEN** a channel `C9` top-level @mention arrives with ts `300.3`
- **THEN** the bot replies in a thread rooted at `300.3`
- **AND** the adapter derives `session_id="slack:thread:C9:300.3"`

#### Scenario: Slack channel thread reply
- **WHEN** a channel `C9` message arrives with `thread_ts="300.3"`
- **THEN** the adapter derives `session_id="slack:thread:C9:300.3"` (shared by all participants in that thread)

#### Scenario: DM and channel do not collide
- **WHEN** user `U123` has both a DM conversation and a channel @mention
- **THEN** their session ids are namespaced distinctly (`slack:dm:...` vs `slack:thread:...`) and never share history

### Requirement: Normalize Telegram messages
The system SHALL receive Telegram updates via Long Polling and normalize them into `NormalizedMessage`.

#### Scenario: Telegram private chat message
- **WHEN** a Telegram message arrives in a private chat with user `12345`
- **THEN** the adapter creates `NormalizedMessage(platform="telegram", session_id="user:12345", text=<message text>)`

#### Scenario: Telegram group reply chain
- **WHEN** a Telegram group message arrives as a reply to message `msg_id=999`
- **THEN** the adapter creates `NormalizedMessage(session_id="thread:999")`

### Requirement: Unified message format
The system SHALL define `NormalizedMessage` as the contract between adapters and the agent pipeline.

#### Scenario: NormalizedMessage fields
- **WHEN** any adapter normalizes a message
- **THEN** the resulting object MUST contain: `platform`, `session_id`, `user_id`, `text`, `attachments` (list, may be empty), `reply_func` (async callable)
- **AND** MAY contain `progress_func` (optional async callable, default `None`); when `None` the pipeline behaves identically to the previous version
- **AND** MAY contain `session_context` (optional, default `None`) carrying sender/channel metadata; when `None` no context is injected

#### Scenario: Adapter without optional fields preserves existing behavior
- **WHEN** an adapter constructs `NormalizedMessage` without `progress_func` or `session_context`
- **THEN** normalizer.route() runs identically to the pre-change version with no side effects

### Requirement: Thread-first replies
The system SHALL always reply within a thread context, never as a top-level channel message.

#### Scenario: Reply goes into thread
- **WHEN** agent produces a response for a Slack channel message
- **THEN** the adapter sends the reply as a thread reply, not a new channel message

### Requirement: IM SDK reconnect
The system SHALL automatically reconnect if the IM SDK connection drops, AND SHALL report each connection lifecycle transition to the connector registry (`im_connector_store.report_status` / `heartbeat`) so the status is observable.

#### Scenario: Slack Socket Mode reconnect
- **WHEN** the Slack WebSocket connection drops
- **THEN** the Slack SDK automatically reconnects without manual intervention
- **AND** the adapter reports `status="disconnected"` on drop and `status="connected"` once reconnected

#### Scenario: Telegram polling reconnect
- **WHEN** the Telegram Long Polling request fails with a network error
- **THEN** the adapter retries with exponential backoff
- **AND** the adapter reports `status="error"` with the error message, then `status="connected"` on recovery

#### Scenario: Heartbeat while connected
- **WHEN** an adapter is connected and serving
- **THEN** it periodically calls `heartbeat(platform)` so `last_heartbeat_at` stays fresh

### Requirement: Adapter startup is connector-driven and credentials come from the registry

Owner-level adapters (Telegram, WhatsApp) SHALL be started and stopped by the connector
manager (not hardcoded in server lifespan) and SHALL obtain credentials via
`im_connector_config.resolve(platform)` (DB-first, `.env` fallback). Slack SHALL NOT be
started this way: each agent's Slack connection is started per-agent from the agent
index (see `per-agent-slack-connector`), with credentials from that agent's
`im.slack` environment references.

#### Scenario: Manager starts enabled owner-level adapters on boot
- **WHEN** the server starts and the `telegram` connector is `enabled=1` with valid credentials
- **THEN** the connector manager launches the Telegram adapter using credentials from `resolve("telegram")`

#### Scenario: Slack is not started by the owner connector manager
- **WHEN** the server starts
- **THEN** no Slack adapter is launched by the owner-level connector manager; Slack connections are started per-agent from the agent index

#### Scenario: Disabled adapter not started
- **WHEN** the `telegram` connector is `enabled=0` at boot
- **THEN** the Telegram adapter is not launched

### Requirement: Routing enforces the channel allowlist
Before normalizing into the agent pipeline, `normalizer.route` SHALL consult `im_channel_allowlist.is_allowed(platform, channel_id, workspace_id)` and SHALL drop disallowed messages before user-level checks.

#### Scenario: Allowed channel routes normally
- **WHEN** a message arrives in a channel allowed by the platform's enforcement policy
- **THEN** routing proceeds to the IM user allowlist check and agent resolution as before

#### Scenario: Disallowed channel dropped pre-pipeline
- **WHEN** the platform has `allowlist_enforced=1` and the message's channel/workspace is not listed
- **THEN** the adapter replies with a rejection and the message never reaches the agent loop

#### Scenario: Existing NormalizedMessage contract preserved
- **WHEN** an allowed message is normalized
- **THEN** the `NormalizedMessage` fields and thread-first reply behavior are unchanged from the prior spec

### Requirement: Slack approval interactivity

The Slack adapter SHALL render permission-gate approval prompts as Block Kit messages
with three interactive buttons — approve, reject, and approve-always — each carrying the
approval id in its action value. The adapter SHALL register a Socket Mode `block_actions`
handler that maps the clicked action to a gate decision, passing the **clicking user's
Slack id** (from the interaction payload) as the decision actor so the gate's
authorization check applies. On an accepted decision the adapter SHALL update the
original prompt message to a result state with the buttons removed; on a rejected
decision (unauthorized actor or expired approval) it SHALL show the clicker an
ephemeral notice and leave the prompt intact. The `approve <id>` / `reject <id>` text
commands SHALL keep working on all platforms. **In a channel the bot must be @-mentioned
to be addressed, so the adapter SHALL recognize the `approve`/`reject <id>` text command
even when the message is prefixed with a leading bot mention, by stripping a single
leading `<@id>` (optionally `<@id|label>`) before matching; the id format check is
unchanged, so ordinary prose that merely @-mentions the bot is not misread as approval.**

#### Scenario: approval prompt renders buttons

- **WHEN** the permission gate sends an approval prompt through a Slack reply or a Slack
  outbound DM
- **THEN** the message carries Block Kit actions `approval_approve`, `approval_reject`,
  and `approval_approve_always` with the approval id as their value

#### Scenario: authorized click resolves and updates the message

- **WHEN** an authorized actor clicks 批准 (approve) on the prompt
- **THEN** the gate resolves the approval with the clicker's Slack id and the original
  message is updated to a result state without buttons

#### Scenario: approve-always click grants the allow-always fingerprint

- **WHEN** an authorized actor clicks 始终允许 (approve always)
- **THEN** the gate resolves with `always=True`, persisting the allow-always grant

#### Scenario: unauthorized click is rejected with an ephemeral notice

- **WHEN** a user who is not an authorized decision actor clicks any approval button
- **THEN** the approval stays pending, the prompt keeps its buttons, and the clicker
  receives an ephemeral notice

#### Scenario: text command fallback unaffected

- **WHEN** a user replies `approve <id>` instead of clicking
- **THEN** the decision flows through the existing text-command path unchanged

#### Scenario: platforms without blocks degrade to text

- **WHEN** the approval prompt is delivered via a reply channel that does not accept a
  `blocks` argument (e.g. Telegram, TUI)
- **THEN** the plain-text prompt with the `approve <id>` / `reject <id>` instructions is
  sent instead

#### Scenario: channel approve with a leading bot mention resolves

- **WHEN** a user in a channel replies `<@bot> approve <id>` (the bot must be @-mentioned
  to receive the message)
- **THEN** the adapter strips the single leading mention, recognizes the `approve <id>`
  text command, and resolves the approval — instead of treating it as a new agent turn

#### Scenario: prose that mentions the bot is not misread as approval

- **WHEN** a user sends `<@bot> approve the plan` (no valid approval id)
- **THEN** the leading mention is stripped but the id-format check fails, so the message
  is handled as a normal agent turn, not an approval decision

