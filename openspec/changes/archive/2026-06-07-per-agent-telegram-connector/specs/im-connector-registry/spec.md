## MODIFIED Requirements

### Requirement: Slack and Telegram are excluded from the owner-level connector lifecycle

The owner-level connector registry SHALL NOT start Slack or Telegram. `start_all_enabled`
SHALL skip Slack and Telegram rows; both are supervised per-agent from the agent index (see
`per-agent-slack-connector` and `per-agent-telegram-connector`). Existing `im_connectors`
Slack/Telegram rows MAY remain but SHALL be inert (never started by the owner-level manager).

#### Scenario: start_all_enabled skips Slack

- **WHEN** `start_all_enabled` runs and an `enabled=1` `slack` row exists in `im_connectors`
- **THEN** no Slack adapter is started by the owner-level connector manager

#### Scenario: start_all_enabled skips Telegram

- **WHEN** `start_all_enabled` runs and an `enabled=1` `telegram` row exists in `im_connectors`
- **THEN** no Telegram adapter is started by the owner-level connector manager
