## MODIFIED Requirements

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
