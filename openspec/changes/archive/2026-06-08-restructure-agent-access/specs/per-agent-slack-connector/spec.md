## MODIFIED Requirements

### Requirement: agent.yaml declares a Slack connector

An agent SHALL declare its Slack connection in its `agent.yaml` under `connectors.slack`
with `bot_token_env` and `app_token_env` (environment-variable names, never inline tokens)
and an optional `access: ConnectorAccess` block. The `channels` field is removed; channel
filtering is handled by `access.allow_channels`. Tokens SHALL be resolved from the named
environment variables at connection time. The config scanner SHALL reject inline plaintext
secrets anywhere under `connectors`.

#### Scenario: Connector parsed with env references

- **WHEN** an `agent.yaml` declares `connectors.slack` with `bot_token_env: SUPPORT_SLACK_BOT`
  and `app_token_env: SUPPORT_SLACK_APP`
- **THEN** the agent loads with a Slack connector whose tokens resolve from those env vars

#### Scenario: Inline token rejected

- **WHEN** an `agent.yaml` sets `connectors.slack.bot_token_env` to an inline token-like
  value (e.g. `xoxb-...`) instead of an env-var name
- **THEN** the scan fails fast, naming the agent and field

#### Scenario: No connector block

- **WHEN** an `agent.yaml` has no `connectors.slack`
- **THEN** the agent loads normally and no Slack connection is started for it

#### Scenario: Connector with access block

- **WHEN** an `agent.yaml` declares `connectors.slack` with `access.allow_users: ["U123"]`
- **THEN** the agent loads and only user `U123` is allowed to interact via Slack

### Requirement: Slack routing resolves the agent implicitly from the connection

For Slack, the agent SHALL be determined by the connection that received the event, not
by a channel→agent lookup. The adapter SHALL stamp the resolved agent onto the
`NormalizedMessage`, and routing SHALL use it directly without calling
`get_agent_for_context`. Channel filtering (formerly `connectors.slack.channels`) is
now handled by the access gate via `access.allow_channels`.

#### Scenario: Message handled by the receiving agent

- **WHEN** a Slack message arrives on agent `support`'s connection
- **THEN** the message is processed with agent `support`'s snapshot, with no
  channel→agent lookup

#### Scenario: Channel filter via access.allow_channels

- **WHEN** agent `support` sets `connectors.slack.access.allow_channels: ["C1"]` and a message arrives
  in channel `C2`
- **THEN** the message is rejected by the access gate

#### Scenario: Empty allow_channels responds everywhere

- **WHEN** agent `support` omits `connectors.slack.access.allow_channels` (or leaves it empty)
- **THEN** the agent responds in every channel its Slack app receives events from

## REMOVED Requirements

### Requirement: connectors.slack.channels field

**Reason**: Replaced by `connectors.slack.access.allow_channels`. Having two channel-filter fields at different levels caused configuration confusion and required users to maintain the same channel IDs in two places.

**Migration**: Move any `connectors.slack.channels` entries to `connectors.slack.access.allow_channels`.
