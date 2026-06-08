## MODIFIED Requirements

### Requirement: agent.yaml declares a Slack connector

An agent SHALL declare its Slack connection in its `agent.yaml` under `connectors.slack`
with `bot_token_env` and `app_token_env` (environment-variable names, never inline tokens)
and an optional `access: ConnectorAccess` block. The token SHALL be resolved from the named
environment variables at connection time.

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

### Requirement: Slack adapter responds only to @mention in channels, all messages in DMs

The Slack adapter SHALL register two event handlers:
- `app_mention`: handles all @mentions of the bot in channels
- `message` filtered to `channel_type == "im"`: handles direct messages

Regular channel messages that do not @mention the bot SHALL be ignored. The Slack application
MUST have the `app_mention` event subscription enabled in its Event Subscriptions configuration.

#### Scenario: @mention in channel triggers response

- **WHEN** a user sends `<@BOT_USER_ID> hello` in a channel
- **THEN** the message is routed to the agent loop via the `app_mention` handler

#### Scenario: DM without mention triggers response

- **WHEN** a user sends a direct message to the bot without any @mention
- **THEN** the message is routed to the agent loop via the `message` handler

#### Scenario: Channel message without mention is ignored

- **WHEN** a user sends a message in a channel without @mentioning the bot
- **THEN** the message is NOT routed to the agent loop

### Requirement: Slack routing resolves the agent implicitly from the connection

For Slack, the agent SHALL be determined by the connection that received the event, not
by a channel→agent lookup. The adapter SHALL stamp the resolved agent onto the
`NormalizedMessage`, and routing SHALL use it directly. Channel filtering is handled
by the access gate via `access.allow_channels`.

#### Scenario: Message handled by the receiving agent

- **WHEN** a Slack @mention arrives on agent `support`'s connection
- **THEN** the message is processed with agent `support`'s snapshot, with no channel→agent lookup

#### Scenario: Channel filter via access.allow_channels

- **WHEN** agent `support` sets `connectors.slack.access.allow_channels: ["C1"]` and an
  @mention arrives in channel `C2`
- **THEN** the message is rejected by the access gate

#### Scenario: Empty allow_channels responds everywhere

- **WHEN** agent `support` omits `connectors.slack.access.allow_channels` (or leaves it empty)
- **THEN** the agent responds in every channel its Slack app receives @mention events from
