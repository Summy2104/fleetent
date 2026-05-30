## MODIFIED Requirements

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
Adapters SHALL be started and stopped by the connector manager (not hardcoded in server lifespan), and SHALL obtain credentials via `im_connector_config.resolve(platform)` (DB-first, `.env` fallback) rather than reading `config.Settings` directly.

#### Scenario: Manager starts enabled adapters on boot
- **WHEN** the server starts and the `slack` connector is `enabled=1` with valid credentials
- **THEN** the connector manager launches the Slack adapter using credentials from `resolve("slack")`

#### Scenario: Disabled adapter not started
- **WHEN** the `telegram` connector is `enabled=0` at boot
- **THEN** the Telegram adapter is not launched

#### Scenario: Credentials sourced from DB when seeded
- **WHEN** `im_connectors.slack.config` has been seeded with a token
- **THEN** the adapter uses the DB token, ignoring the `.env` value

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
