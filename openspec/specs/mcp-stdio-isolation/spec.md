# mcp-stdio-isolation Specification

## Purpose
TBD - created by archiving change mcp-stdio-isolation. Update Purpose after archive.
## Requirements
### Requirement: stdio subprocess receives a minimal safe environment

When launching a stdio MCP server subprocess (both startup registration and the admin connectivity probe), the client SHALL pass an environment composed of a vetted whitelist of host variables (those needed for a process to run, such as `PATH` and `HOME`) plus the server's explicitly declared `env`. The client SHALL NOT pass the full platform process environment to the subprocess, so platform secrets (database URLs, API keys, service tokens) are not inherited by a third-party MCP server.

#### Scenario: Platform secrets not inherited
- **WHEN** the platform process environment contains a secret variable that is not on the whitelist and a stdio server declares some `env`
- **THEN** the subprocess environment passed to that server does not contain the secret variable

#### Scenario: Essential host variables still provided
- **WHEN** a stdio MCP server is launched
- **THEN** the subprocess environment includes the whitelisted host variables that are present (e.g. `PATH`) so the command can be found and run

#### Scenario: Probe uses the same isolation as registration
- **WHEN** the admin connectivity probe launches a stdio server
- **THEN** it passes the same minimal safe environment, not the full platform environment

### Requirement: Explicit server env preserved and takes precedence

The server's explicitly declared `env` entries SHALL be present in the subprocess environment and SHALL override a whitelisted host value of the same name. This is the supported, auditable way to forward a specific value (including a host secret) to a stdio MCP server.

#### Scenario: Declared env entries present
- **WHEN** a stdio server declares `env` with a key `FOO`
- **THEN** the subprocess environment contains `FOO` with the declared value

#### Scenario: Declared env overrides whitelist
- **WHEN** a stdio server declares `env` with a key that is also a whitelisted host variable
- **THEN** the subprocess environment uses the server-declared value for that key

