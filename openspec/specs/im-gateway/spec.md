## Purpose

Receive messages from IM platforms (Slack, Telegram) via their SDKs, normalize them
into a uniform `NormalizedMessage` contract, and route them through the agent pipeline
with thread-first replies and automatic SDK reconnect.
## Requirements
### Requirement: Normalize Slack messages
The system SHALL receive Slack events via Socket Mode and normalize them into a `NormalizedMessage` before routing to the agent pipeline.

#### Scenario: Slack DM message
- **WHEN** a Slack DM message arrives from user `U123`
- **THEN** the adapter creates `NormalizedMessage(platform="slack", session_id="user:U123", user_id=<internal>, text=<message text>)`

#### Scenario: Slack thread reply
- **WHEN** a Slack message with `thread_ts="T456"` arrives
- **THEN** the adapter creates `NormalizedMessage(session_id="thread:T456")`

#### Scenario: Slack channel message without thread
- **WHEN** a Slack channel message arrives without a thread_ts
- **THEN** the bot replies in a new thread (bot creates the thread), and `session_id = "thread:{new_thread_ts}"`

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
`connectors.slack` environment references.

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

