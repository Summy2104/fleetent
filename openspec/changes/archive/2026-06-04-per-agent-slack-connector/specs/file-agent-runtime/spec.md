## ADDED Requirements

### Requirement: Agent file may declare platform connectors

The agent file model SHALL accept an optional `connectors` block declaring per-agent
platform connections, and SHALL validate it. Per-platform connector semantics are
defined by the relevant connector capability (e.g. `per-agent-slack-connector`). Secret
material under `connectors` MUST be referenced by environment-variable name only.

#### Scenario: connectors block accepted

- **WHEN** an `agent.yaml` includes a `connectors.slack` block with env-reference token names
- **THEN** the agent loads with that connector declaration available to the connector layer

#### Scenario: connectors block optional

- **WHEN** an `agent.yaml` omits `connectors`
- **THEN** the agent loads normally

## MODIFIED Requirements

### Requirement: Secrets rejected in agent files

The scan SHALL reject any agent file containing an inline plaintext secret, anywhere in
the file including the `mcp_servers` and `connectors` subtrees. Secret material SHALL be
referenced only by environment-variable name (e.g. `api_key_env`, `bot_token_env`,
`app_token_env`, `credential_ref`).

#### Scenario: Inline plaintext secret is rejected

- **WHEN** an agent file's `mcp_servers` entry contains an inline token-like value
  instead of an `api_key_env` reference
- **THEN** the scan fails fast with an error identifying the file and field

#### Scenario: Inline secret under connectors is rejected

- **WHEN** an agent file's `connectors.slack.bot_token_env` holds an inline token-like
  value instead of an environment-variable name
- **THEN** the scan fails fast, identifying the agent and field

#### Scenario: Env reference is accepted

- **WHEN** an agent file references secrets only by env-var name (e.g.
  `api_key_env: ACME_MCP_TOKEN`, `bot_token_env: SUPPORT_SLACK_BOT`)
- **THEN** the scan accepts the file
