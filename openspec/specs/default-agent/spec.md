# default-agent Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
### Requirement: Global default agent configuration

The system SHALL determine the default agent from the file-based agent index: the
single agent whose file sets `bindings.default: true`. When a message has no channel or
user binding, that default agent (if present) is used. Resolving the default SHALL NOT
read the database.

#### Scenario: Default agent declared in a file, no channel or user binding

- **WHEN** exactly one agent file sets `bindings.default: true` and neither the channel
  nor the user has a binding
- **THEN** that agent is applied to the request, resolved from its file with no DB read

#### Scenario: No default agent declared

- **WHEN** no agent file sets `bindings.default: true`
- **THEN** default resolution returns nothing and the request proceeds with no agent
  (bare run)

### Requirement: Agent lookup priority order

The system SHALL resolve the agent for each incoming message in the following priority
order, served entirely from the file-based agent index: channel binding > user binding
> default agent > bare run.

#### Scenario: All levels present — channel wins

- **WHEN** the channel is bound by an agent file, the user is bound by an agent file,
  and a default agent file exists
- **THEN** the channel's agent is used

#### Scenario: No channel binding — user wins

- **WHEN** no agent file binds the channel but an agent file binds the user
- **THEN** the user's agent is used

#### Scenario: No channel or user binding — default wins

- **WHEN** neither the channel nor the user is bound by any agent file
- **THEN** the default agent (if declared) is used

#### Scenario: No bindings and no default — bare run

- **WHEN** no agent file binds the channel or user and none declares a default
- **THEN** the request runs without a custom system_prompt or allowed_tools

### Requirement: Admin can set default agent via CLI
The admin CLI SHALL provide a `set-default-agent` command.

#### Scenario: Set default agent
- **WHEN** admin runs `fleetent-admin set-default-agent --agent-name basic`
- **THEN** `config/settings.yaml` is updated with `default_agent_name: basic`

#### Scenario: Clear default agent
- **WHEN** admin runs `fleetent-admin set-default-agent --clear`
- **THEN** `default_agent_name` is removed from `config/settings.yaml`

