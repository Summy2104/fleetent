## MODIFIED Requirements

### Requirement: Admin can set default agent via CLI
The admin CLI SHALL provide a `set-default-agent` command that operates on the file-based
agent config. Setting a default SHALL write `bindings.default: true` to the target agent's
`agent.yaml` (and clear it from any previously-default agent); clearing SHALL remove the
`bindings.default` flag. The command MUST NOT write `default_agent_name` to
`config/settings.yaml` — that field is removed from `Settings`.

#### Scenario: Set default agent
- **WHEN** admin runs `fleetent-admin set-default-agent --agent-name basic`
- **THEN** agent `basic`'s `agent.yaml` has `bindings.default: true`
- **AND** no `default_agent_name` is written to `config/settings.yaml`

#### Scenario: Clear default agent
- **WHEN** admin runs `fleetent-admin set-default-agent --clear`
- **THEN** the `bindings.default` flag is removed from the previously-default agent's `agent.yaml`
