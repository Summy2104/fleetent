## MODIFIED Requirements

### Requirement: Configuration templates
install script SHALL seed a flat agent home: `.env` at `FLEETENT_HOME/.env` and the self-contained single-agent config at `FLEETENT_HOME/agent.yaml`（home 根，无 `config/` 子目录）from repository templates under `config/agent/`, preserving existing operator files. Global settings/mcp templates remain unseeded.

#### Scenario: Fresh install seeds flat home agent yaml
- **WHEN** `FLEETENT_HOME/agent.yaml` or `.env` is absent
- **THEN** script creates `$FLEETENT_HOME/.env` from `config/agent/.env.example`
- **AND** creates `$FLEETENT_HOME/agent.yaml` from `config/agent/agent.yaml.example`
- **AND** does not create a `$FLEETENT_HOME/config/` subdirectory

#### Scenario: Existing home agent yaml or env is preserved
- **WHEN** `$FLEETENT_HOME/agent.yaml` or `.env` already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed `agent.yaml` or `.env`
