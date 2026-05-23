## ADDED Requirements

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
The system SHALL automatically reconnect if the IM SDK connection drops.

#### Scenario: Slack Socket Mode reconnect
- **WHEN** the Slack WebSocket connection drops
- **THEN** the Slack SDK automatically reconnects without manual intervention

#### Scenario: Telegram polling reconnect
- **WHEN** the Telegram Long Polling request fails with a network error
- **THEN** the adapter retries with exponential backoff
