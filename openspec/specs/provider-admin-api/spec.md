# provider-admin-api Specification

## Purpose
TBD - created by archiving change 2026-06-02-model-provider-management. Update Purpose after archive.
## Requirements
### Requirement: Provider listing with routing context
The admin console SHALL list every configured provider showing its name, `base_url`, `model`, owning task_type(s), its priority position within each task_type fallback chain, and last connectivity status. The `api_key` SHALL never appear in plaintext.

#### Scenario: List shows masked key and routing position
- **WHEN** an admin opens the provider list
- **THEN** each provider shows name, base_url, model, owning task_type(s), fallback priority position, and last connectivity status, with the `api_key` masked (prefix + `***` or full `***`) — never plaintext

### Requirement: Create, edit, and delete a provider
An admin SHALL be able to add, edit, and delete a provider by supplying `base_url`, `model`, `api_key` (masked storage and display), `max_tokens`, `temperature`, and `extra_params` (provider-specific passthrough). Saving SHALL take effect without restarting the service, via the fleetent config write boundary. Deleting SHALL remove the provider from configuration and from all task_type routes.

#### Scenario: Add provider takes effect without restart
- **WHEN** an admin adds a provider with base_url / model / api_key / max_tokens / temperature / extra_params
- **THEN** the provider is persisted via the config write boundary and the next routing resolution reflects it without a service restart, and the stored `api_key` is masked in every view

#### Scenario: Edit leaves key unchanged when blank
- **WHEN** an admin edits a provider and leaves the api_key field blank
- **THEN** the existing key is preserved unchanged and no plaintext key is returned in the response

#### Scenario: Delete provider writes audit
- **WHEN** an admin deletes a provider and confirms
- **THEN** the provider is removed from configuration and from all task_type routes, and the delete action is written to the audit log

### Requirement: Per-provider and per-model observability view
The console SHALL show, per provider / model, call count, token usage, cost (only when a price is configured), error rate, average latency, and which task_types / Agents use it. The data source is the observability domain; this surface only aggregates by provider·model.

#### Scenario: Observability aggregation by provider and model
- **WHEN** an admin views the per-provider observability panel
- **THEN** call count, token usage, error rate, average latency, and consuming task_types / Agents are shown per provider·model, with cost shown only when a unit price is configured for that model

### Requirement: api_key never disclosed in plaintext
Across every view, response body, audit `detail`, and log line, the provider `api_key` SHALL be masked and never returned in plaintext. Masking SHALL be applied in a single shared serialization layer.

#### Scenario: No plaintext key in any response or audit
- **WHEN** any `/admin/providers/*` response or audit `detail` is produced for a provider that has an api_key
- **THEN** the api_key appears only as a masked placeholder and the plaintext never appears in the body, audit detail, or logs

### Requirement: Role-gated provider management
Provider create / edit / delete SHALL be restricted to `admin` / `built_in_admin`. A `viewer` SHALL only browse provider configuration (key masked) and observability. Requests without a valid login session SHALL be rejected with 401.

#### Scenario: Viewer cannot modify provider configuration
- **WHEN** a viewer opens the model_provider management page and attempts to add / edit / delete a provider or change routing order
- **THEN** the relevant controls are hidden or the request returns 403; the viewer may only browse configuration (key masked), routing order, and observability

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to any `/admin/providers/*` endpoint carries no valid login session
- **THEN** the response is 401

