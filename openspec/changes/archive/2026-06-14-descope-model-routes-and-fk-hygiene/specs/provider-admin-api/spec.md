# provider-admin-api Delta

## MODIFIED Requirements

### Requirement: Provider listing with routing context
The admin console SHALL list every configured provider showing its name, `base_url`, `model`, and last connectivity status. The `api_key` SHALL never appear in plaintext. （`model_routes` descope 后，listing 不再展示 owning task_type / fallback priority position——task-type 路由真相源是 `ROUTES_PATH` YAML / agent.yaml，不再有按 provider 反查 task_type 的管理库表。）

#### Scenario: List shows masked key
- **WHEN** an admin opens the provider list
- **THEN** each provider shows name, base_url, model, and last connectivity status, with the `api_key` masked (prefix + `***` or full `***`) — never plaintext

### Requirement: Create, edit, and delete a provider
An admin SHALL be able to add, edit, and delete a provider by supplying `base_url`, `model`, `api_key` (masked storage and display), `max_tokens`, `temperature`, and `extra_params` (provider-specific passthrough). Saving SHALL take effect without restarting the service, via the fleetent config write boundary. Deleting SHALL remove the provider from configuration（`model_routes` descope 后不再需要连带清理 task_type 路由表）。

#### Scenario: Add provider takes effect without restart
- **WHEN** an admin adds a provider with base_url / model / api_key / max_tokens / temperature / extra_params
- **THEN** the provider is persisted via the config write boundary and is available to model resolution without a service restart, and the stored `api_key` is masked in every view

#### Scenario: Edit leaves key unchanged when blank
- **WHEN** an admin edits a provider and leaves the api_key field blank
- **THEN** the existing key is preserved unchanged and no plaintext key is returned in the response

#### Scenario: Delete provider writes audit
- **WHEN** an admin deletes a provider and confirms
- **THEN** the provider is removed from configuration and the delete action is written to the audit log
