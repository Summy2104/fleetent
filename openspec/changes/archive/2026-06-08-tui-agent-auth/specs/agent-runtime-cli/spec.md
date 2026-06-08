# agent-runtime-cli Delta Spec

## ADDED Requirements

### Requirement: agent init generates TUI token in .env

`fleetent agent init` SHALL append `FLEETENT_TUI_TOKEN=ma-<64hex>` to the agent's `.env`
when the `.env` does not already contain a `FLEETENT_TUI_TOKEN` entry. The token is
generated with `secrets.token_hex(32)`.

#### Scenario: .env contains FLEETENT_TUI_TOKEN after init

- **WHEN** `fleetent agent init my-bot` is run
- **THEN** `~/.fleetent/agents/my-bot/.env` SHALL contain a non-empty `FLEETENT_TUI_TOKEN` value
