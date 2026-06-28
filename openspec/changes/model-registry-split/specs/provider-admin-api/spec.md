## MODIFIED Requirements

### Requirement: Provider listing with routing context
The admin console SHALL list every configured provider showing its id, `vendor`, optional default `base_url`, and last connectivity status, plus the count of models under it. The `api_key` SHALL never appear in plaintext. A provider row SHALL NOT carry a `model` field — concrete callable targets are listed via the separate model listing. Listing exposes no owning task_type / fallback priority position; runtime routing truth lives in agent-level `model_overrides`, not in a management DB table.

#### Scenario: List shows masked key and model count
- **WHEN** an admin opens the provider list
- **THEN** each provider shows id, vendor, default base_url, model count, and last connectivity status, with the `api_key` masked (prefix + `***` or full `***`) — never plaintext
- **AND** no provider row carries a `model` field

### Requirement: Create, edit, and delete a provider
An admin SHALL be able to add, edit, and delete a provider by supplying `vendor`, optional default `base_url`, and `api_key` (masked storage and display) plus optional `api_key_env`. A provider body SHALL NOT accept `model`, `max_tokens`, `temperature`, or per-model `params` — those belong to models. Saving SHALL take effect without restarting the service, via the fleetent config write boundary.

#### Scenario: Add provider takes effect without restart
- **WHEN** an admin adds a provider with vendor / optional base_url / api_key (and optional api_key_env)
- **THEN** the provider is persisted via the config write boundary and is available for models to reference without a service restart, and the stored `api_key` is masked in every view

#### Scenario: Provider body rejects per-model fields
- **WHEN** an admin submits a provider create/edit body containing `model` or `temperature`
- **THEN** those fields are not persisted on the provider (they are model-level concerns)

#### Scenario: Edit leaves key unchanged when blank
- **WHEN** an admin edits a provider and leaves the api_key field blank
- **THEN** the existing key is preserved unchanged and no plaintext key is returned in the response

#### Scenario: Delete provider writes audit
- **WHEN** an admin deletes a provider with no models under it and confirms
- **THEN** the provider is removed from configuration and the delete action is written to the audit log

## ADDED Requirements

### Requirement: Create, edit, and delete a model
An admin SHALL be able to add, edit, and delete a model under a provider by supplying `provider_id` (required), `protocol` (required), `model_name`, the connection target (`base_url` for chat protocols, `endpoint` for embedding/rerank/image protocols), `max_tokens`, per-1k input/output prices, and `params`. A model SHALL NOT carry any api_key field; its credential is the owning provider's `api_key_env`. Saving SHALL take effect without restarting the service.

#### Scenario: Add a model under a provider
- **WHEN** an admin adds a model with `provider_id`, `protocol=openai_chat`, `model_name`, and `base_url`
- **THEN** the model is persisted under that provider and becomes selectable for agent routes, with no api_key field on the model

#### Scenario: Protocol determines required connection target
- **WHEN** an admin adds a model with `protocol=http_embedding`
- **THEN** the model requires `endpoint`; a model with `protocol=openai_chat` requires `base_url`

#### Scenario: Delete model writes audit
- **WHEN** an admin deletes an unreferenced model and confirms
- **THEN** the model is removed and the delete action is written to the audit log

### Requirement: Model-level connectivity test
The connectivity test SHALL operate on a model (the concrete callable unit: its `base_url`/`endpoint` + `model_name` + the owning provider's key), not on a bare provider. The probe SHALL NOT record observability usage/cost.

#### Scenario: Connectivity test on a model
- **WHEN** an admin runs a connectivity test on a model
- **THEN** the request reaches the model's connection target using the owning provider's credential and returns reachability/latency, without recording usage

### Requirement: Reference reverse-lookup and guarded deletion
The API SHALL expose, per model and per provider, which agents/routes reference it, computed by scanning `agents.model_overrides` (including recognition of legacy-form references). Deletion SHALL be guarded: deleting a referenced model SHALL return a conflict listing the referencing agents/routes; deleting a provider that still has models SHALL return a conflict.

#### Scenario: Look up references of a model
- **WHEN** an admin requests the references of a model
- **THEN** the response lists each referencing agent and route key, derived from `agents.model_overrides`

#### Scenario: Deleting a referenced model is rejected
- **WHEN** an admin attempts to delete a model that at least one agent route references
- **THEN** the request returns a conflict and the model is not deleted

#### Scenario: Deleting a provider with models is rejected
- **WHEN** an admin attempts to delete a provider that still has at least one model
- **THEN** the request returns a conflict and the provider is not deleted
