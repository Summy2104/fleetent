## MODIFIED Requirements

### Requirement: Single-file agent home loading

Agent runtime SHALL load a self-contained Agent home at `agents/<agent-id>/`. The default installed
Agent SHALL live at `agents/default/agent.yaml`. Root `agent.yaml` single-file mode is not a
current MVP deployment path.

#### Scenario: Default Agent home is loaded
- **WHEN** runtime loads the default installed Agent
- **THEN** it reads `agents/default/agent.yaml`
- **AND** it does not require `agent.yaml` at Platform home root

#### Scenario: Explicit Agent home is loaded
- **WHEN** operator runs `fleetent agent run support`
- **THEN** runtime reads `agents/support/agent.yaml` by default
- **AND** `--home` may still override the Agent home path

#### Scenario: Root agent yaml is not the default path
- **WHEN** `FLEETENT_HOME/agent.yaml` exists
- **THEN** runtime does not treat it as the canonical default deployment config
- **AND** docs instruct operators to use `agents/<agent-id>/agent.yaml`
