## MODIFIED Requirements

### Requirement: Platform materializes model config

Platform deployment SHALL materialize authored model targets/routes into the Agent's
`agent.yaml`. It SHALL seed `.env` with missing `api_key_env` names and SHALL preserve existing
operator-provided values. Plaintext model API keys SHALL NOT be written to `agent.yaml`. When
the platform-authored `model_overrides` explicitly configures only a subset of standard routes,
materialize SHALL merge those routes onto the default local model policy one route at a time —
routes not present in `model_overrides` SHALL keep their default target rather than being
dropped.

#### Scenario: Materialize writes models
- **WHEN** platform deploys an Agent with authored model targets/routes
- **THEN** the generated `agent.yaml` contains the fully resolved `models` section

#### Scenario: Materialize seeds env without overwriting
- **WHEN** `.env` already contains a value for a model `api_key_env`
- **THEN** materialize preserves that value
- **AND** adds only missing model env names with empty values

#### Scenario: Unconfigured routes keep platform defaults
- **WHEN** an agent's `model_overrides` only configures the `default` route
- **THEN** the materialized `agent.yaml` SHALL still contain the default local targets for
  `memory_extraction`, `kb_extraction`, `vision`, and `embedding` rather than omitting them
