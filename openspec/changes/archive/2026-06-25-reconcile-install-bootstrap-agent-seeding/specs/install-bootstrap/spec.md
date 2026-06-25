## MODIFIED Requirements

### Requirement: Configuration templates

install script SHALL seed explicit Platform home config templates from runtime-adjacent repository
examples. It SHALL create `.env`(from `.env.example`)and `platform.yaml`(from
`platform.yaml.example`)in `FLEETENT_HOME`, independent of any Agent home. It SHALL preserve
existing operator files. 默认 Agent home **不**由安装脚本 seed(见 requirement "Install bootstrap
seeds explicit Platform and Agent homes")。

#### Scenario: Fresh install seeds Platform home
- **WHEN** operator runs install with an empty `FLEETENT_HOME`
- **THEN** script creates `$FLEETENT_HOME/.env` from `.env.example`
- **AND** creates `$FLEETENT_HOME/platform.yaml` from `platform.yaml.example`
- **AND** does not create a Platform home config subdirectory
- **AND** does not create any default Agent home

#### Scenario: Existing Platform files are preserved
- **WHEN** `$FLEETENT_HOME/.env` or `$FLEETENT_HOME/platform.yaml` already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed Platform config/env files
