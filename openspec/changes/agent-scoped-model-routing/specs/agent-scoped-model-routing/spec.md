## ADDED Requirements

### Requirement: Agent-local model targets

`agent.yaml` SHALL define a required `models.targets` list. Each target SHALL have a unique
`id`, a non-empty `provider`, and a `protocol`. `provider` SHALL be treated as display,
audit, billing, and authoring metadata; runtime behavior SHALL be selected by `protocol`,
not by provider-specific branching.

#### Scenario: OpenAI-compatible chat target
- **WHEN** an Agent defines a target with `protocol: openai_chat`
- **THEN** the target must provide `base_url` and `model`
- **AND** it may provide `api_key_env`, `max_tokens`, and `params`

#### Scenario: HTTP embedding target
- **WHEN** an Agent defines a target with `protocol: http_embedding`
- **THEN** the target must provide `endpoint`
- **AND** it may provide `model` and `api_key_env`

#### Scenario: HTTP rerank target
- **WHEN** an Agent defines a target with `protocol: http_rerank`
- **THEN** the target must provide `endpoint`
- **AND** it may provide `model` and `api_key_env`

#### Scenario: OpenAI-compatible image generation target
- **WHEN** an Agent defines a target with `protocol: openai_image_generation`
- **THEN** the target must provide `endpoint` and `model`
- **AND** it may provide `api_key_env`

#### Scenario: Duplicate target id is invalid
- **WHEN** `models.targets` contains duplicate `id` values
- **THEN** Agent config loading fails loudly

### Requirement: Agent-local model routes

`agent.yaml` SHALL define `models.routes` as a mapping from route key to ordered target entries.
The ordered entries SHALL represent fallback priority. A route entry SHALL reference a target by
id and MAY override `max_tokens` and `params`.

#### Scenario: Route resolves target chain in order
- **WHEN** a route contains `primary` then `backup`
- **THEN** runtime resolves and tries `primary` before `backup`

#### Scenario: Route entry overrides target params
- **WHEN** a target has `params.temperature: 0.5`
- **AND** a route entry for that target has `params.temperature: 0`
- **THEN** the resolved call config uses `temperature: 0`

#### Scenario: Route entry overrides max_tokens
- **WHEN** a target has `max_tokens: 4096`
- **AND** a route entry has `max_tokens: 1024`
- **THEN** the resolved call config uses `max_tokens: 1024`

#### Scenario: Missing target reference is invalid
- **WHEN** a route entry references a target id that is not in `models.targets`
- **THEN** Agent config loading fails loudly

### Requirement: Standard route keys

The runtime SHALL recognize the following model route keys: `default`, `memory_extraction`,
`vision`, `embedding`, `rerank`, `image_generation`, `audio_transcription`, and
`audio_generation`. `image_generation` SHALL route the existing `generate_image` tool through an
OpenAI-compatible images provider. Audio routes MAY exist before their adapters are fully
implemented, but their names SHALL be reserved.

#### Scenario: Default chat route
- **WHEN** the agent loop needs a normal LLM call
- **THEN** it resolves `models.routes.default`

#### Scenario: Memory extraction route
- **WHEN** memory extraction needs a model call
- **THEN** it resolves `models.routes.memory_extraction`

#### Scenario: Embedding and rerank routes
- **WHEN** embedding or rerank providers are needed
- **THEN** runtime resolves `models.routes.embedding` or `models.routes.rerank`

#### Scenario: Image generation route
- **WHEN** the `generate_image` tool needs to create an image
- **THEN** runtime resolves `models.routes.image_generation`

### Requirement: API key env contract

Model target credentials SHALL be referenced with optional `api_key_env`. The default generated
environment variable name SHALL be `FLEETENT_MODEL_<TARGET_ID_UPPER>_API_KEY`. The runtime SHALL
read the API key from the current Agent process environment and SHALL NOT require a provider-specific
name such as `ANTHROPIC_API_KEY`.

#### Scenario: Target with api_key_env
- **WHEN** a target declares `api_key_env`
- **THEN** the runtime uses that environment variable value when calling the target

#### Scenario: Missing api_key_env value
- **WHEN** a target declares `api_key_env` but the variable is missing at call time
- **THEN** the call fails with a configuration error and does not fallback

#### Scenario: No-auth local target
- **WHEN** a target omits `api_key_env`
- **THEN** the runtime may call it without an API key

### Requirement: Runtime uses Agent-scoped resolver

Runtime model calls SHALL resolve model configuration from the active Agent snapshot's
`models` section. Runtime SHALL NOT use `config/routes.yaml` or built-in production routes as
the primary source of model routing.

#### Scenario: Agent-specific route is used
- **WHEN** two Agents define different `models.routes.default`
- **THEN** each Agent runtime uses its own configured route

#### Scenario: routes.yaml is not the runtime source
- **WHEN** `config/routes.yaml` exists but the Agent snapshot defines `models`
- **THEN** runtime uses the Agent snapshot `models`

### Requirement: Platform materializes model config

Platform deployment SHALL materialize authored model targets/routes into the Agent's
`agent.yaml`. It SHALL seed `.env` with missing `api_key_env` names and SHALL preserve existing
operator-provided values. Plaintext model API keys SHALL NOT be written to `agent.yaml`.

#### Scenario: Materialize writes models
- **WHEN** platform deploys an Agent with authored model targets/routes
- **THEN** the generated `agent.yaml` contains the fully resolved `models` section

#### Scenario: Materialize seeds env without overwriting
- **WHEN** `.env` already contains a value for a model `api_key_env`
- **THEN** materialize preserves that value
- **AND** adds only missing model env names with empty values

### Requirement: Old model config is removed

MVP runtime SHALL reject or remove old `model_overrides` configuration and SHALL not depend on
`config/routes.yaml` as a production route source.

#### Scenario: model_overrides is not accepted
- **WHEN** an Agent config uses `model_overrides` instead of `models`
- **THEN** config loading fails loudly

#### Scenario: Default templates use generic model env names
- **WHEN** `fleetent agent init` or example config generates model credentials
- **THEN** it uses `FLEETENT_MODEL_<TARGET_ID_UPPER>_API_KEY`
- **AND** it does not use `ANTHROPIC_API_KEY`
