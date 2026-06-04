## MODIFIED Requirements

### Requirement: Configuration templates
install script SHALL seed `.env` at `FLEETENT_HOME/.env` and the self-contained single-agent config at `FLEETENT_HOME/config/agent.yaml` from repository templates, preserving existing operator files. Global settings/mcp templates remain unseeded.

#### Scenario: Fresh install seeds config-dir agent yaml
- **WHEN** `FLEETENT_HOME/config/agent.yaml` or `.env` is absent
- **THEN** script creates `$FLEETENT_HOME/.env` from `.env.example`
- **AND** creates `$FLEETENT_HOME/config/agent.yaml` from `config/agent.yaml.example`

#### Scenario: Existing config-dir agent yaml or env is preserved
- **WHEN** `$FLEETENT_HOME/config/agent.yaml` or `.env` already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed `config/agent.yaml` or `.env`
