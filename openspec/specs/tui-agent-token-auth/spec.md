# tui-agent-token-auth Specification

## Purpose
standalone agent 通过 `FLEETENT_TUI_TOKEN` env var 完成 TUI WebSocket `/ws` 认证，
无需 platform `user_store`。`fleetent agent init` 自动生成 token，开发者无需额外操作。

## Requirements

### Requirement: /ws endpoint authenticates via FLEETENT_TUI_TOKEN

The standalone agent's `/ws` WebSocket endpoint SHALL authenticate connections using
`FLEETENT_TUI_TOKEN` from the process environment. It SHALL NOT call `user_store.authenticate()`.
On success, the connection SHALL proceed with `user_id="local"`.

#### Scenario: Valid token accepted

- **WHEN** a TUI client connects to `/ws` with `Authorization: Bearer <FLEETENT_TUI_TOKEN>`
- **THEN** the connection SHALL be accepted
- **AND** the session SHALL use `user_id="local"`

#### Scenario: Invalid token rejected

- **WHEN** a TUI client connects with a token that does not match `FLEETENT_TUI_TOKEN`
- **THEN** the WebSocket SHALL be closed with code 1008 (Policy Violation)

#### Scenario: Missing FLEETENT_TUI_TOKEN rejects all connections

- **WHEN** `FLEETENT_TUI_TOKEN` is not set in the process environment
- **THEN** every `/ws` connection attempt SHALL be rejected with code 1008
- **AND** the agent SHALL log a message prompting the user to add `FLEETENT_TUI_TOKEN` to `.env`

### Requirement: agent init generates FLEETENT_TUI_TOKEN in .env

`fleetent agent init` SHALL write `FLEETENT_TUI_TOKEN=ma-<64hex>` to the agent's `.env`
file. The token SHALL be generated using a cryptographically secure random source.

#### Scenario: Fresh init produces token in .env

- **WHEN** `fleetent agent init my-bot` is run on a new directory
- **THEN** `.env` SHALL contain a line `FLEETENT_TUI_TOKEN=ma-<64hex>`

#### Scenario: Existing .env is not overwritten

- **WHEN** `fleetent agent init --force my-bot` is run on a directory with an existing `.env`
- **THEN** the existing `.env` is preserved (current behaviour: `.env` not overwritten by init)

### Requirement: managed-agent materialize provisions FLEETENT_TUI_TOKEN

Managed (node-deployed) agents do not run `fleetent agent init`, so platform
materialization SHALL provision `FLEETENT_TUI_TOKEN` for them. When materializing an
agent home, if no token is present it SHALL generate `ma-<64hex>` from a
cryptographically secure source; an existing operator-provided value SHALL be preserved.
The token SHALL be delivered to the node via the existing secret path and SHALL NOT
appear in plaintext in the desired-state config payload.

#### Scenario: Managed agent gets a token without agent init

- **WHEN** the platform materializes a managed agent whose `.env` has no
  `FLEETENT_TUI_TOKEN`
- **THEN** a `FLEETENT_TUI_TOKEN=ma-<64hex>` is provisioned for that agent so its
  `/chat` and `/ws` gateway endpoints can authenticate node-forwarded ingress

#### Scenario: Existing managed token is preserved

- **WHEN** the managed agent already has an operator-set `FLEETENT_TUI_TOKEN`
- **THEN** materialization keeps the existing value rather than regenerating it

#### Scenario: Managed token never leaks into desired-state config

- **WHEN** the desired-state payload for the agent is produced
- **THEN** the `FLEETENT_TUI_TOKEN` value does not appear in the non-secret config payload
  and is delivered only via the secret path
