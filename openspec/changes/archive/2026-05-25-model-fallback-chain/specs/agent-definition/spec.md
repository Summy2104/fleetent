## MODIFIED Requirements

### Requirement: Route configuration schema
`RouteConfig` defines the LLM routing parameters for a task type. It SHALL contain: `base_url`, `model`, `api_key_env`, `max_tokens`, and an optional `fallbacks` ordered sequence of model names to try when the primary model is unavailable.

#### Scenario: RouteConfig with fallbacks
- **WHEN** `RouteConfig` is instantiated with `fallbacks=("claude-haiku-4-5",)`
- **THEN** the config holds a valid fallback sequence accessible as `config.fallbacks`

#### Scenario: RouteConfig without fallbacks remains valid
- **WHEN** `RouteConfig` is instantiated without the `fallbacks` parameter
- **THEN** `config.fallbacks` is an empty tuple and the config is fully valid
