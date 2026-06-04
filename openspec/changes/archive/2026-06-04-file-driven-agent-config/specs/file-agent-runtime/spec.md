## ADDED Requirements

### Requirement: Self-contained agent config file

The system SHALL load each agent from a self-contained file at
`config/agents/<name>/agent.yaml` (directory per agent, fixed filename). The agents
root directory SHALL be an injectable constant overridable by the `FLEETENT_AGENTS_DIR`
environment variable. The agent's identity SHALL be the directory name, which MUST
equal the in-file `name` field.

The file SHALL fully describe the agent with these fields: `name`, `version`
(integer, corresponds to the authoring DB version), `tenant_id`, `team_id`,
`system_prompt`, `model_overrides`, `memory_namespace`, `skills_dir` (nullable;
null means the global default), `allowed_skills` (empty means no narrowing),
`allowed_tools`, `plugins`, `features` (e.g. `code_execution`, `sandbox_env`), inline
`mcp_servers`, and `bindings` (`default`, `channels`, `users`).

#### Scenario: Valid file resolves to an AgentSnapshot

- **WHEN** `config/agents/support/agent.yaml` exists with `name: support` and a valid schema
- **THEN** loading agent `support` returns an `AgentSnapshot` whose `system_prompt`,
  `allowed_tools`, `skills_dir`, `model_overrides`, and `memory_namespace` come from
  that file, and whose identity is the name `support`

#### Scenario: Directory name must match in-file name

- **WHEN** `config/agents/support/agent.yaml` declares `name: helpdesk`
- **THEN** the scan fails fast with an error naming the file and the mismatch

#### Scenario: FLEETENT_AGENTS_DIR overrides the agents root

- **WHEN** `FLEETENT_AGENTS_DIR` points at a temporary directory containing
  `assistant/agent.yaml`
- **THEN** agent `assistant` is resolved from that directory and `config/agents/` is
  not read

### Requirement: Zero-database runtime resolution

Resolving an agent and its routing at runtime SHALL NOT perform any database access.
The agent definition, bindings, and inline MCP servers SHALL be served entirely from
the in-memory index built by scanning the agents directory.

#### Scenario: Runtime path performs no DB access

- **WHEN** an agent is resolved and run from files while the database layer is rigged
  to raise on any access
- **THEN** resolution and the run proceed without raising, proving no DB call occurred

### Requirement: Scan-built in-memory index

The system SHALL scan the agents directory and build an in-memory index mapping agent
name to definition, `(platform, channel_id)` to agent name, `user_id` to agent name,
and the set of default agents. The server SHALL scan once at startup; the CLI SHALL
scan per invocation.

#### Scenario: Index built from multiple agent files

- **WHEN** the agents directory contains `support/agent.yaml` and `sales/agent.yaml`
- **THEN** the index resolves both names, and each agent's channels and users map back
  to its name

#### Scenario: Empty or missing agents directory yields no agents

- **WHEN** the agents directory is absent or empty
- **THEN** the index is empty and agent lookups return nothing (bare run), with no error

### Requirement: Inline MCP overlay without database

Per-agent MCP servers SHALL be defined inline in the agent file as full server
definitions. Effective MCP resolution SHALL overlay the agent's inline `mcp_servers`
onto the global defaults with no database lookup.

#### Scenario: Inline MCP overlaid on defaults

- **WHEN** an agent file defines an inline `mcp_servers` entry with id `acme`
- **THEN** the effective MCP server set for that agent includes `acme` overlaid on the
  global defaults, resolved without any database access

### Requirement: Secrets rejected in agent files

The scan SHALL reject any agent file containing an inline plaintext secret. Secret
material SHALL be referenced only by environment-variable name (e.g. `api_key_env`,
`credential_ref`).

#### Scenario: Inline plaintext secret is rejected

- **WHEN** an agent file's `mcp_servers` entry contains an inline token-like value
  instead of an `api_key_env` reference
- **THEN** the scan fails fast with an error identifying the file and field

#### Scenario: Env reference is accepted

- **WHEN** an agent file's `mcp_servers` entry sets `api_key_env: ACME_MCP_TOKEN` and
  no inline secret
- **THEN** the scan accepts the file

### Requirement: Binding conflicts fail fast

The scan SHALL reject configurations where two agents claim the same channel, the same
user, or where more than one agent declares itself the default.

#### Scenario: Two agents bind the same channel

- **WHEN** `support/agent.yaml` and `sales/agent.yaml` both list channel `slack:C123`
- **THEN** the scan fails fast with an error naming the conflicting channel and agents

#### Scenario: Multiple default agents

- **WHEN** two agent files both set `bindings.default: true`
- **THEN** the scan fails fast with an error naming the conflicting agents
