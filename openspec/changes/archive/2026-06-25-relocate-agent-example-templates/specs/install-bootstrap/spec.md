## MODIFIED Requirements

### Requirement: Configuration templates

install script SHALL seed explicit Platform home files and the default Agent home from
runtime-adjacent repository examples. It SHALL create `.env` and `platform.yaml` in
`FLEETENT_HOME`, and `agents/default/agent.yaml`, `agents/default/.env`, and
`agents/default/data/` under the same Platform home. It SHALL preserve existing operator files.

> 注:本 requirement 与后续 "Install bootstrap seeds explicit Platform and Agent homes"
> requirement 在"是否 seed 默认 Agent home"上存在预存矛盾(与模板物理位置无关),留待单独
> change 收口。本次仅把模板**来源**路径同步到根目录。

#### Scenario: Fresh install seeds Platform home and default Agent home
- **WHEN** operator runs install with an empty `FLEETENT_HOME`
- **THEN** script creates `$FLEETENT_HOME/.env` from `.env.example`
- **AND** creates `$FLEETENT_HOME/platform.yaml` from `platform.yaml.example`
- **AND** creates `$FLEETENT_HOME/agents/default/agent.yaml` from `agent.yaml.example`
- **AND** creates `$FLEETENT_HOME/agents/default/.env` from `agent.env.example`
- **AND** creates `$FLEETENT_HOME/agents/default/data/`
- **AND** does not create a Platform home config subdirectory

#### Scenario: Existing Platform or Agent files are preserved
- **WHEN** `$FLEETENT_HOME/.env`, `$FLEETENT_HOME/platform.yaml`,
  `$FLEETENT_HOME/agents/default/agent.yaml`, or `$FLEETENT_HOME/agents/default/.env`
  already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed Platform or Agent config/env files
