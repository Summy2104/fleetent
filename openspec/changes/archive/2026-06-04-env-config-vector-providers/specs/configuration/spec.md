## ADDED Requirements

### Requirement: Vector provider config uses env references
Embedding and rerank HTTP provider configuration SHALL support environment-variable references for deploy-time provider values while keeping secrets out of tracked YAML.

#### Scenario: Embedding HTTP provider env references
- **WHEN** `settings.yaml` configures `embedding.backend: http`
- **THEN** endpoint, model, and dimensions may be supplied through `endpoint_env`, `model_env`, and `dimensions_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint`, `model`, and `dimensions` fields remain compatible

#### Scenario: Rerank HTTP provider env references
- **WHEN** `settings.yaml` configures `rerank.backend: http`
- **THEN** endpoint and model may be supplied through `endpoint_env` and `model_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint` and `model` fields remain compatible

#### Scenario: Templates expose smoke env names without secrets
- **WHEN** operator views `.env.example` and `config/settings.yaml.example`
- **THEN** the files show the env var names used by real embedding and rerank smoke
- **AND** the files do not contain provider API key values
