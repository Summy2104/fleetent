## MODIFIED Requirements

### Requirement: Secrets rejected in agent files

The scan SHALL reject any agent file containing an inline plaintext secret in
secret-bearing fields, including the `mcp_servers` and `connectors` subtrees. Secret
material SHALL be referenced only by environment-variable name (e.g. `api_key_env`,
`bot_token_env`, `app_token_env`, `credential_ref`) or by an `env:VAR_NAME` reference in
free-form value maps such as `mcp_servers[*].env` and `mcp_servers[*].headers`.

The scan SHALL NOT flag structural, non-secret fields — command names (`command`),
command arguments (`args`, e.g. an npm package spec like `@scope/mcp-server-x`), server
ids (`id`), and transport names (`transport`). The scan SHALL still inspect `url` values,
which may embed credentials.

#### Scenario: Inline plaintext secret is rejected

- **WHEN** an agent file's `mcp_servers` entry contains an inline token-like value in an
  `env` or `headers` value instead of an env reference
- **THEN** the scan fails fast with an error identifying the file and field

#### Scenario: npm package spec in args is not flagged

- **WHEN** an agent file's `mcp_servers[*].args` contains a package spec like
  `@aashari/mcp-server-atlassian-jira`
- **THEN** the scan does not treat it as an inline secret and the file loads

#### Scenario: env: reference is accepted in env and headers

- **WHEN** an agent file references secrets via `env:VAR_NAME` in `mcp_servers[*].env` or
  `mcp_servers[*].headers` values (e.g. `ATLASSIAN_API_TOKEN: env:JIRA_TOKEN`,
  `X-API-Key: env:MIDDLE_KEY`)
- **THEN** the scan accepts the file

#### Scenario: Env-var-name reference is accepted

- **WHEN** an agent file references secrets only by env-var name (e.g.
  `api_key_env: ACME_MCP_TOKEN`, `bot_token_env: SUPPORT_SLACK_BOT`)
- **THEN** the scan accepts the file

#### Scenario: Secret embedded in url is still rejected

- **WHEN** an agent file's `mcp_servers[*].url` embeds an inline token-like value
- **THEN** the scan fails fast, identifying the field
