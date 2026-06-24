## MODIFIED Requirements

### Requirement: Secrets rejected in agent files

The scan SHALL reject any agent file containing an inline plaintext secret in
secret-bearing fields, including the `mcp_servers` and `im` subtrees. Secret
material SHALL be referenced only by environment-variable name (e.g. `api_key_env`,
`bot_token_env`, `app_token_env`, `credential_ref`) or by an `env:VAR_NAME` reference in
free-form value maps such as `mcp_servers[*].env` and `mcp_servers[*].headers`.

The scan SHALL NOT flag structural, non-secret fields — command names (`command`),
command arguments (`args`, e.g. an npm package spec like `@scope/mcp-server-x`), server
ids (`id`), and transport names (`transport`). The scan SHALL still inspect `url` values,
which may embed credentials.

The scan SHALL NOT flag IM access allowlist entries — values under
`im.<platform>.access.allow_users` and `im.<platform>.access.allow_groups`. These are id
lists (internal user ids — which are UUIDs — and group ids), not credentials; the platform
materializes internal user ids (UUIDs) into `allow_users`, and a UUID's length/entropy
would otherwise trip the inline-secret heuristic. This exemption SHALL be scoped to those
two access paths only and SHALL NOT relax scanning of any secret-bearing field under `im`
(e.g. `bot_token_env`, `app_token_env`).

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

#### Scenario: IM access allowlist with internal user UUID is not flagged

- **WHEN** an agent file's `im.slack.access.allow_users` (or `im.telegram.access.allow_groups`)
  contains an internal user id in UUID form (e.g. `5f5904ef-efcf-42bb-82fa-ad5a150b078c`),
  as materialized by the platform for an agent bound to a user
- **THEN** the scan does not treat it as an inline secret and the file loads

#### Scenario: Inline token in im binding is still rejected

- **WHEN** an agent file sets `im.slack.bot_token_env` to an inline token-like value
  (e.g. `xoxb-...`) instead of an env-var name
- **THEN** the scan fails fast, naming the agent and field

#### Scenario: Secret embedded in url is still rejected

- **WHEN** an agent file's `mcp_servers[*].url` embeds a credential (e.g. `?token=...`)
- **THEN** the scan fails fast with an error identifying the file and field
