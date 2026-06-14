# mcp-stdio-isolation Specification

## Purpose
TBD - created by archiving change mcp-stdio-isolation. Update Purpose after archive.
## Requirements
### Requirement: stdio subprocess receives a minimal safe environment

When launching a stdio MCP server subprocess (both startup registration and the admin connectivity probe), the client SHALL pass an environment composed of, in ascending precedence: a vetted whitelist of host variables (those needed for a process to run, such as `PATH` and `HOME`), the **convention-injected file-location layer**, and the server's explicitly declared `env`. The client SHALL NOT pass the full platform process environment to the subprocess, so platform secrets (database URLs, API keys, service tokens) are not inherited by a third-party MCP server.

The convention-injected layer SHALL set `XDG_DATA_HOME`, `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` to the per-server partition tree `<agent_home>/exchange/<server_id>/{data,config,cache}`, and the subprocess working directory (`cwd`) SHALL be set to the `data` partition. Only the `data` partition participates in the `/exchange` namespace; `config` and `cache` MUST stay outside it. A server's explicitly declared `env` value for any of these variables SHALL override the convention-injected value (existing deployments keep their trees in place).

#### Scenario: Platform secrets not inherited

- **WHEN** the platform process environment contains a secret variable that is not on the whitelist and a stdio server declares some `env`
- **THEN** the subprocess environment passed to that server does not contain the secret variable

#### Scenario: Essential host variables still provided

- **WHEN** a stdio MCP server is launched
- **THEN** the subprocess environment includes the whitelisted host variables that are present (e.g. `PATH`) so the command can be found and run

#### Scenario: Probe uses the same isolation as registration

- **WHEN** the admin connectivity probe launches a stdio server
- **THEN** it passes the same minimal safe environment, not the full platform environment

#### Scenario: Convention injection for an unconfigured server

- **WHEN** a stdio server declares no `XDG_*` env of its own
- **THEN** the subprocess receives `XDG_DATA_HOME=<agent_home>/exchange/<server_id>/data`, `XDG_CONFIG_HOME=…/config`, `XDG_CACHE_HOME=…/cache`, and its working directory is the `data` partition

#### Scenario: Explicit env overrides convention injection

- **WHEN** a stdio server explicitly declares `XDG_DATA_HOME` in agent.yaml
- **THEN** the subprocess receives the explicitly declared value, not the convention-injected one

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

### Requirement: file_isolation escape hatch disables convention injection

A stdio server config MAY declare `file_isolation: off`; the client MUST then skip the convention-injected file-location layer for that server (whitelist + explicit `env` only, working directory unchanged), so servers that need the host user's real `~/.config`/XDG locations keep them. The default (`file_isolation` absent) MUST be injection enabled.

#### Scenario: file_isolation off keeps host locations

- **WHEN** a stdio server declares `file_isolation: off` and no explicit `XDG_*` env
- **THEN** the subprocess environment contains no convention-injected `XDG_*` values and its working directory is not redirected

#### Scenario: Default is injection on

- **WHEN** a stdio server declares neither `file_isolation` nor explicit `XDG_*` env
- **THEN** the convention-injected layer applies

