## ADDED Requirements

### Requirement: materialize provisions FLEETENT_TUI_TOKEN for managed agents

Managed (node-deployed) agents do not run `fleetent agent init`, so platform materialization SHALL provision `FLEETENT_TUI_TOKEN` for them: when materializing an agent's home, if no token is present it SHALL generate `ma-<64hex>` from a cryptographically secure source; an existing operator-provided value SHALL be preserved. The token SHALL be delivered to the node via the existing secret path and SHALL NOT appear in plaintext in the desired-state config payload.

#### Scenario: Managed agent gets a token without agent init

- **WHEN** the platform materializes a managed agent whose `.env` has no `FLEETENT_TUI_TOKEN`
- **THEN** a `FLEETENT_TUI_TOKEN=ma-<64hex>` is provisioned for that agent so its `/ws` gateway can authenticate the node forwarder

#### Scenario: Existing token is preserved

- **WHEN** the agent already has an operator-set `FLEETENT_TUI_TOKEN`
- **THEN** materialization keeps the existing value rather than regenerating it

#### Scenario: Token never leaks into desired-state config

- **WHEN** the desired-state payload for the agent is produced
- **THEN** the `FLEETENT_TUI_TOKEN` value does not appear in the non-secret config payload; it is delivered only via the secret path
