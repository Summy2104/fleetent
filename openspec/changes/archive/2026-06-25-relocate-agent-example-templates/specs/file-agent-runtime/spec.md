## MODIFIED Requirements

### Requirement: Single-file agent home loading

Agent runtime SHALL load a self-contained Agent home at
`FLEETENT_HOME/tenants/<tenant-id>/agents/<agent-id>/`(默认租户为 `default`)。The default
standalone/dev Agent SHALL resolve to `FLEETENT_HOME/tenants/default/agents/<agent-id>/agent.yaml`。
Root `agent.yaml` single-file mode is not a current MVP deployment path.

#### Scenario: Default Agent home is loaded
- **WHEN** runtime loads the default standalone Agent
- **THEN** it reads `FLEETENT_HOME/tenants/default/agents/<agent-id>/agent.yaml`
- **AND** it does not require `agent.yaml` at Platform home root

#### Scenario: Explicit Agent home is loaded
- **WHEN** operator runs `fleetent agent run support`
- **THEN** runtime reads `FLEETENT_HOME/tenants/default/agents/support/agent.yaml` by default
- **AND** `--home` may still override the Agent home path

#### Scenario: Root agent yaml is not the default path
- **WHEN** a root-level Agent YAML exists in Platform home
- **THEN** runtime does not treat it as the canonical default deployment config
- **AND** docs instruct operators to use `tenants/<tenant-id>/agents/<agent-id>/agent.yaml`
