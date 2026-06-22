## MODIFIED Requirements

### Requirement: Apply owns the agent definition only, never bindings
The apply API SHALL only own the agent definition: `name` (immutable identity), `system_prompt` / `allowed_tools` / `model_overrides` (mutable). `model_overrides` is OPTIONAL: when present it carries the agent's model routing policy (the `{routes: {<route_key>: [target entries]}}` shape that mirrors agent.yaml's `models` section) and SHALL be threaded into the agent version snapshot via `agent_store.create_version(model_overrides=...)`; when absent the existing model policy is left unchanged. Bindings (`user_agents` and default bindings) are runtime state and SHALL NOT be overwritten or deleted by apply.

#### Scenario: Apply does not touch bindings
- **WHEN** an existing managed agent has user bindings and a new apply updates its `system_prompt`
- **THEN** the `system_prompt` is updated and all existing `user_agents` rows are preserved unchanged

#### Scenario: Immutable name is restored on apply
- **WHEN** an existing managed agent's `name` was changed in the UI and an apply for that agent (matched by `agent_id`) carries the spec `name`
- **THEN** the `name` is force-restored to the spec value

#### Scenario: Apply sets model_overrides on the agent definition
- **WHEN** an apply carries a non-empty `model_overrides` for an agent
- **THEN** the value is persisted into the agent version snapshot via `create_version(model_overrides=...)`, and a subsequent materialize of that agent produces the configured model routing policy rather than the `default_models()` placeholder

#### Scenario: Apply without model_overrides leaves model policy unchanged
- **WHEN** an apply omits `model_overrides` (or sends it as null)
- **THEN** no model policy is written by this apply and the agent's existing model behavior is unchanged (a fresh agent still falls back to `default_models()`)

## ADDED Requirements

### Requirement: Managed agent model config carries provider env names, never secrets
The apply API's `model_overrides` SHALL only carry the model routing structure including `api_key_env` (the environment variable NAME that holds the provider credential). It SHALL NOT carry secret values. The credential value SHALL be delivered through the existing agent secrets path (`/admin/agents/{name}/secrets`) and injected by the node via desired state.

#### Scenario: model_overrides references a key env, secret supplied separately
- **WHEN** an apply sets `model_overrides` whose target declares `api_key_env: FLEETENT_MODEL_PRIMARY_API_KEY` and a separate secrets write supplies that env's value
- **THEN** the materialized agent.yaml references `api_key_env` for the target and the node injects the secret value at launch, with no secret value persisted in the agent definition or version snapshot
