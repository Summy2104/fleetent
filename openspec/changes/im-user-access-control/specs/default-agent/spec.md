## ADDED Requirements

### Requirement: Global default agent configuration
The system SHALL support configuring a default agent by name via `Settings.default_agent_name`. When a message has no channel or user binding, the default agent (if configured) is used.

#### Scenario: Default agent configured, no channel or user binding
- **WHEN** `Settings.default_agent_name = "basic"` and neither the channel nor the user has an agent binding
- **THEN** `agent_store.get_default_agent()` returns the agent named "basic" and it is applied to the request

#### Scenario: Default agent not configured
- **WHEN** `Settings.default_agent_name` is `None` (or empty)
- **THEN** `agent_store.get_default_agent()` returns `None` and the request proceeds with no agent (bare run)

#### Scenario: Default agent name refers to non-existent agent
- **WHEN** `Settings.default_agent_name = "nonexistent"` and no agent with that name exists
- **THEN** `agent_store.get_default_agent()` returns `None` and the request proceeds as bare run

### Requirement: Agent lookup priority order
The system SHALL resolve the agent for each incoming message in the following priority order: channel binding > user binding > default agent > bare run.

#### Scenario: All levels present — channel wins
- **WHEN** the channel has a binding, the user has a binding, and a default agent is configured
- **THEN** the channel's agent is used

#### Scenario: No channel binding — user wins
- **WHEN** the channel has no binding but the user has a binding
- **THEN** the user's agent is used

#### Scenario: No channel or user binding — default wins
- **WHEN** neither channel nor user is bound
- **THEN** the default agent (if configured) is used

#### Scenario: No bindings and no default — bare run
- **WHEN** no channel binding, no user binding, and no default agent configured
- **THEN** the request runs without a custom system_prompt or allowed_tools

### Requirement: Admin can set default agent via CLI
The admin CLI SHALL provide a `set-default-agent` command.

#### Scenario: Set default agent
- **WHEN** admin runs `mini-agent-admin set-default-agent --agent-name basic`
- **THEN** `config/settings.yaml` is updated with `default_agent_name: basic`

#### Scenario: Clear default agent
- **WHEN** admin runs `mini-agent-admin set-default-agent --clear`
- **THEN** `default_agent_name` is removed from `config/settings.yaml`
