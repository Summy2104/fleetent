# per-agent-slack-connector Specification

## Purpose
TBD - created by archiving change per-agent-slack-connector. Update Purpose after archive.
## Requirements
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

### Requirement: One Socket Mode connection per declaring agent

The system SHALL run exactly one Slack Socket Mode connection per agent whose
`connectors.slack` env tokens resolve, supervised by agent name and sourced from the
agent index. Startup SHALL start a connection for every such agent. An agent whose env
tokens are missing SHALL be reported unconfigured/error and skipped without affecting
other agents' connections.

#### Scenario: Two agents each get their own connection

- **WHEN** agents `support` and `sales` each declare `connectors.slack` with resolvable
  env tokens and startup runs
- **THEN** two independent Socket Mode connections are started, one per agent

#### Scenario: Missing token isolates failure

- **WHEN** agent `support` declares `connectors.slack` but its `bot_token_env` variable
  is unset, while `sales` resolves fine
- **THEN** `support` is reported unconfigured/error and skipped, and `sales` still starts

### Requirement: Reload reconciles connections against the agent index

The supervisor SHALL provide a reload that re-scans the agent index and reconciles
running connections against declared ones: starting newly declared agents, stopping
removed ones, and restarting agents whose connector config changed.

#### Scenario: New agent added then reloaded

- **WHEN** a new agent declaring `connectors.slack` is added and reload runs
- **THEN** a connection is started for the new agent without restarting the others

#### Scenario: Agent removed then reloaded

- **WHEN** an agent that had a running Slack connection is removed and reload runs
- **THEN** that agent's connection is stopped and removed

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

### Requirement: Connector carries no owner_id and reads no platform table

The Slack connector path SHALL NOT thread an `owner_id` and SHALL NOT read any platform
management table (notably `users`). The supervisor's runner signature SHALL be
`(agent_name, config)` — no `owner_id` argument — and `slack.run` / `create_app` SHALL NOT
accept an `owner_id`. The inbound `NormalizedMessage` SHALL NOT carry an `owner_id` field.
Session identity SHALL be derived without an owner prefix: the routed `session_id` equals
the adapter-derived session id (`channel_type` + `channel_id` + `user_id` + `thread_root`),
NOT `f"{owner_id}:{session_id}"`. User and channel access remain enforced by the normalizer
access gate against `msg.user_id` and the connector `access` block, independent of any owner.

#### Scenario: Standalone connector starts without a users table

- **WHEN** `fleetent agent run` starts a Slack connector in an environment where the
  platform `users` table does not exist (no `management.db` / no platform boot)
- **THEN** the connection starts, the supervisor never reads a platform table, and no
  `no such table: users` error is logged

#### Scenario: Adapter stamps agent and user but not owner

- **WHEN** the Slack handler normalizes an inbound message on agent `support`'s connection
- **THEN** the routed `NormalizedMessage` carries `agent_name="support"` and the sender's
  `user_id`, and has no `owner_id`

#### Scenario: Session id has no owner prefix

- **WHEN** a Slack DM from user `U123` is routed
- **THEN** the session id used for load/save/lock is the adapter-derived id with no
  `<owner>:` prefix

