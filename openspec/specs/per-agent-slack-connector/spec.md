# per-agent-slack-connector Specification

## Purpose
TBD - created by archiving change per-agent-slack-connector. Update Purpose after archive.
## Requirements
### Requirement: agent.yaml declares a Slack connector

An agent SHALL declare its Slack connection in its `agent.yaml` under
`connectors.slack` with `bot_token_env` and `app_token_env` (environment-variable
names, never inline tokens) and an optional `channels` list. Tokens SHALL be resolved
from the named environment variables at connection time. The config scanner SHALL
reject inline plaintext secrets anywhere under `connectors`.

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
`get_agent_for_context`. When `connectors.slack.channels` is non-empty, events from
channels not in the list SHALL be ignored.

#### Scenario: Message handled by the receiving agent

- **WHEN** a Slack message arrives on agent `support`'s connection
- **THEN** the message is processed with agent `support`'s snapshot, with no
  channel→agent lookup

#### Scenario: Channel filter drops unlisted channels

- **WHEN** agent `support` sets `connectors.slack.channels: ["C1"]` and a message arrives
  in channel `C2`
- **THEN** the message is ignored

#### Scenario: Empty channel filter responds everywhere

- **WHEN** agent `support` omits `connectors.slack.channels` (or leaves it empty)
- **THEN** the agent responds in every channel its Slack app receives events from

