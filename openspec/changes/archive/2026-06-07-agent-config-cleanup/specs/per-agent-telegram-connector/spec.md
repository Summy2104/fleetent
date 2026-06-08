## ADDED Requirements

### Requirement: Official agent.yaml example includes a Telegram connector block

The `agents/default/agent.yaml.example` SHALL include a `connectors.telegram` example
block showing `bot_token_env` and `channels`, alongside the existing Slack example, so
operators can discover and configure per-agent Telegram connectivity.

#### Scenario: Example file shows telegram connector

- **WHEN** an operator reads `agents/default/agent.yaml.example`
- **THEN** they find a `connectors.telegram` block with `bot_token_env` and `channels` fields

#### Scenario: Corresponding env var in .env.example

- **WHEN** an operator reads `agents/default/.env.example`
- **THEN** they find a placeholder for the Telegram bot token env var referenced in the example
