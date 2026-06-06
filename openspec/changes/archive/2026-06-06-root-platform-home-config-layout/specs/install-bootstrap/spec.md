## MODIFIED Requirements

### Requirement: Configuration templates

install script SHALL seed explicit Platform home files and the default Agent home from
runtime-adjacent repository examples. It SHALL create `.env` and `platform.yaml` in
`FLEETENT_HOME`, and `agents/default/agent.yaml`, `agents/default/.env`, and
`agents/default/data/` under the same Platform home. It SHALL preserve existing operator files.

#### Scenario: Fresh install seeds Platform home and default Agent home
- **WHEN** operator runs install with an empty `FLEETENT_HOME`
- **THEN** script creates `$FLEETENT_HOME/.env` from `.env.example`
- **AND** creates `$FLEETENT_HOME/platform.yaml` from `platform.yaml.example`
- **AND** creates `$FLEETENT_HOME/agents/default/agent.yaml` from
  `agents/default/agent.yaml.example`
- **AND** creates `$FLEETENT_HOME/agents/default/.env` from `agents/default/.env.example`
- **AND** creates `$FLEETENT_HOME/agents/default/data/`
- **AND** does not create `$FLEETENT_HOME/config/`

#### Scenario: Existing Platform or Agent files are preserved
- **WHEN** `$FLEETENT_HOME/.env`, `$FLEETENT_HOME/platform.yaml`,
  `$FLEETENT_HOME/agents/default/agent.yaml`, or `$FLEETENT_HOME/agents/default/.env`
  already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed Platform or Agent config/env files

### Requirement: Install bootstrap seeds explicit Platform and Agent homes

安装脚本 SHALL seed 明确的 Platform home 与默认 Agent home，而不是把 Platform home 根目录同时当成
Agent home。默认 Agent home SHALL be `agents/default/` and SHALL contain `agent.yaml`, `.env`,
and `data/`.

#### Scenario: Default Agent home is under agents/default
- **WHEN** install completes
- **THEN** default Agent config lives at `$FLEETENT_HOME/agents/default/agent.yaml`
- **AND** no default Agent config is created at `$FLEETENT_HOME/agent.yaml`
