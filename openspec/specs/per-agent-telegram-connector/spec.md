# per-agent-telegram-connector Specification

## Purpose
Per-agent Telegram connectivity: each agent declares its own Telegram bot in agent.yaml, is supervised by agent name from the agent index, resolves the agent implicitly from the receiving connection, and filters chats — mirroring per-agent-slack-connector. The adapter carries no platform dependency.

## Requirements

### Requirement: agent.yaml declares a Telegram connector

An agent SHALL declare its Telegram connection in its `agent.yaml` under
`connectors.telegram` with `bot_token_env` (an environment-variable name, never an inline
token) and an optional `access: ConnectorAccess` block. The `channels` field is removed;
chat filtering is handled by `access.allow_channels`. The token SHALL be resolved from
the named environment variable at connection time. The config scanner SHALL reject inline
plaintext secrets anywhere under `connectors`.

#### Scenario: Connector parsed with env reference

- **WHEN** an `agent.yaml` declares `connectors.telegram` with `bot_token_env: SALES_TG_BOT`
- **THEN** the agent loads with a Telegram connector whose token resolves from that env var

#### Scenario: Inline token rejected

- **WHEN** an `agent.yaml` sets `connectors.telegram.bot_token_env` to an inline token-like
  value instead of an env-var name
- **THEN** the scan fails fast, naming the agent and field

#### Scenario: No connector block

- **WHEN** an `agent.yaml` has no `connectors.telegram`
- **THEN** the agent loads normally and no Telegram connection is started for it

#### Scenario: Connector with access block

- **WHEN** an `agent.yaml` declares `connectors.telegram` with `access.require_approval: false`
- **THEN** the agent loads and unknown Telegram users are rejected silently (not queued as pending)

### Requirement: One Telegram connection per declaring agent

The system SHALL run exactly one Telegram polling connection per agent whose
`connectors.telegram` env token resolves, supervised by agent name and sourced from the
agent index. Startup SHALL start a connection for every such agent. An agent whose env
token is missing SHALL be reported unconfigured and skipped without affecting other
agents' connections.

#### Scenario: Two agents each get their own connection

- **WHEN** agents `support` and `sales` each declare `connectors.telegram` with a resolvable
  env token and startup runs
- **THEN** two independent Telegram connections are started, one per agent

#### Scenario: Missing token isolates failure

- **WHEN** agent `support` declares `connectors.telegram` but its `bot_token_env` variable
  is unset, while `sales` resolves fine
- **THEN** `support` is reported unconfigured and skipped, and `sales` still starts

### Requirement: Reload reconciles connections against the agent index

The supervisor SHALL provide a reload that re-scans the agent index and reconciles running
connections against declared ones: starting newly declared agents, stopping removed ones,
and restarting agents whose connector config changed.

#### Scenario: New agent added then reloaded

- **WHEN** a new agent declaring `connectors.telegram` is added and reload runs
- **THEN** a connection is started for the new agent without restarting the others

#### Scenario: Agent removed then reloaded

- **WHEN** an agent that had a running Telegram connection is removed and reload runs
- **THEN** that agent's connection is stopped and removed

### Requirement: Telegram connection status is supervisor-owned, not platform-written

Per-agent Telegram connection status SHALL be owned in-memory by the supervisor
(`unconfigured`/`connecting`/`connected`/`stopped`/`error`). The Telegram adapter SHALL
NOT write status or heartbeat to any platform store and SHALL NOT import
`fleetent.platform`.

#### Scenario: Status transitions tracked by the supervisor

- **WHEN** an agent's Telegram connection starts, then is stopped
- **THEN** the supervisor reports `connected` then `stopped` for that agent, without any
  write to the owner-level `im_connectors` table

#### Scenario: Adapter has no platform dependency

- **WHEN** the Telegram adapter module is imported
- **THEN** it does not import `fleetent.platform`

### Requirement: Telegram routing resolves the agent implicitly from the connection

For Telegram, the agent SHALL be determined by the connection that received the update, not
by a channel→agent lookup. The adapter SHALL stamp the resolved agent onto the
`NormalizedMessage`, and routing SHALL use it directly. Chat filtering (formerly
`connectors.telegram.channels`) is now handled by the access gate via `access.allow_channels`.

#### Scenario: Message handled by the receiving agent

- **WHEN** a Telegram message arrives on agent `sales`'s connection
- **THEN** the message is processed with agent `sales`'s snapshot, with no channel→agent lookup

#### Scenario: Chat filter via access.allow_channels

- **WHEN** agent `sales` sets `connectors.telegram.access.allow_channels: ["-100123"]` and a message
  arrives in chat `-100999`
- **THEN** the message is rejected by the access gate

#### Scenario: Empty allow_channels responds everywhere

- **WHEN** agent `sales` omits `connectors.telegram.access.allow_channels` (or leaves it empty)
- **THEN** the agent responds in every chat its Telegram bot receives updates from
