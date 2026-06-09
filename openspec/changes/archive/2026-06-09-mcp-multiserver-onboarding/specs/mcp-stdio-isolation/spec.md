## MODIFIED Requirements

### Requirement: Explicit server env preserved and takes precedence

The server's explicitly declared `env` entries SHALL be present in the subprocess environment and SHALL override a whitelisted host value of the same name. This is the supported, auditable way to forward a specific value (including a host secret) to a stdio MCP server.

An `env` value of the form `env:VAR_NAME` SHALL be resolved from the parent process environment (populated by the agent `.env`) before being passed to the subprocess: the subprocess receives the resolved value, never the literal `env:VAR_NAME` string. A non-`env:`-prefixed value SHALL be passed through verbatim.

#### Scenario: Declared env entries present
- **WHEN** a stdio server declares `env` with a key `FOO` and a literal value
- **THEN** the subprocess environment contains `FOO` with the declared literal value

#### Scenario: Declared env overrides whitelist
- **WHEN** a stdio server declares `env` with a key that is also a whitelisted host variable
- **THEN** the subprocess environment uses the server-declared value for that key

#### Scenario: env: reference resolved from parent environment
- **WHEN** a stdio server declares `env` with `TOKEN: env:JIRA_TOKEN` and `JIRA_TOKEN` is set in the parent process environment
- **THEN** the subprocess environment contains `TOKEN` with the resolved value of `JIRA_TOKEN`, not the literal `env:JIRA_TOKEN`
