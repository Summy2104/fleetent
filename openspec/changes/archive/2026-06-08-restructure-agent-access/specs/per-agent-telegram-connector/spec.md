## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: connectors.telegram.channels field

**Reason**: Replaced by `connectors.telegram.access.allow_channels`. Mirrors the same consolidation applied to the Slack connector.

**Migration**: Move any `connectors.telegram.channels` entries to `connectors.telegram.access.allow_channels`.
