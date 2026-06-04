## ADDED Requirements

### Requirement: Slack is excluded from the owner-level connector lifecycle

The owner-level connector registry SHALL NOT start Slack. `start_all_enabled` SHALL
skip Slack rows; Slack connections are supervised per-agent from the agent index (see
`per-agent-slack-connector`). Existing `im_connectors` Slack rows MAY remain but SHALL
be inert (never started by the owner-level manager).

#### Scenario: start_all_enabled skips Slack

- **WHEN** `start_all_enabled` runs and an `enabled=1` `slack` row exists in `im_connectors`
- **THEN** no Slack adapter is started by the owner-level connector manager

#### Scenario: Telegram still started by the owner-level manager

- **WHEN** an `enabled=1` `telegram` row exists at boot
- **THEN** the Telegram adapter is started as before
