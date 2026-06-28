# provider-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Providers management tab
The admin console SHALL present a Model Providers tab listing each provider with masked credentials, and SHALL render the models under each provider as a nested second level. Write controls SHALL be admin-only. The tab SHALL NOT show a per-provider health indicator (the former platform health endpoint is removed; provider/model reachability is verified on demand via the connectivity test).

#### Scenario: Admin sees providers with nested models
- **WHEN** an admin opens the Providers tab
- **THEN** each provider is listed via `GET /admin/providers` with credential fields masked, and its models are shown nested beneath it via the model listing

#### Scenario: No health indicator on the tab
- **WHEN** the Providers tab renders
- **THEN** it shows no per-provider health badge and makes no call to a platform health endpoint

#### Scenario: Viewer cannot mutate providers or models
- **WHEN** a viewer opens the Providers tab
- **THEN** create / edit / delete / connectivity-test / pricing controls for both providers and models are hidden

### Requirement: Provider CRUD and connectivity
The console SHALL let an admin create, edit, delete a provider and create, edit, delete a model under it, run a connectivity test on a model, and set per-model pricing, calling the matching `/admin/providers` and `/admin/models` endpoints. Deleting a referenced model or a provider that still has models SHALL surface the returned conflict (with referencing agents/routes) rather than silently failing.

#### Scenario: Connectivity test on a model
- **WHEN** an admin runs a connectivity test on a model
- **THEN** the console calls the model-level connectivity-test endpoint and shows the result

#### Scenario: Guarded delete surfaces references
- **WHEN** an admin attempts to delete a model that is referenced by an agent route
- **THEN** the console surfaces the conflict naming the referencing agents/routes and does not remove the model

### Requirement: Providers managed natively in the React SPA

The React admin SPA SHALL render the providers domain natively (not a deep-link to legacy) and SHALL support the full provider lifecycle against the existing admin API: list, create, edit, delete, run a connectivity test, and set pricing. The provider `api_key` SHALL never be displayed in plaintext in any view or response rendering.

#### Scenario: List providers in the SPA

- **WHEN** an admin opens the providers view in the SPA
- **THEN** providers are listed via `GET /admin/providers` with name, base_url, model, and status, and the api_key is shown masked

#### Scenario: Edit and delete a provider

- **WHEN** an admin edits an existing provider and saves, or deletes one and confirms
- **THEN** the SPA calls `PUT /admin/providers/{id}` (resp. `DELETE /admin/providers/{id}`) and the list refreshes to reflect the change

#### Scenario: Run a connectivity test

- **WHEN** an admin clicks "test" on a provider
- **THEN** the SPA calls `POST /admin/providers/{id}/connectivity-test` and shows the result

#### Scenario: Providers no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** providers is a native route (not an entry in the legacy deep-link list)

### Requirement: Agent model routes are first-class in the console
The agent configuration UI SHALL let an admin configure each standard model route (not only `default`) by selecting a registered model. The `default` route SHALL be presented as required and prominent; the remaining standard routes SHALL be available (advanced section). Each route's model selector SHALL be filtered by the protocol that route expects, so only protocol-compatible models are offered. A route SHALL support an ordered fallback chain (multiple model entries) and optional call-level `max_tokens` / `params` overrides. Selecting a model SHALL write the route entry as a `model_id` reference (no inline connection fields).

#### Scenario: Configure a non-default route
- **WHEN** an admin opens an agent's model routing and selects a model for the `embedding` route
- **THEN** the selector offers only `http_embedding` models, and saving writes `{model_id, ...}` under that route in `model_overrides`

#### Scenario: Protocol filtering prevents mismatch
- **WHEN** an admin opens the `embedding` route selector
- **THEN** chat-protocol models are not listed, so a chat model cannot be assigned to an embedding route

#### Scenario: Fallback chain editing
- **WHEN** an admin adds a second model to the `default` route as a fallback
- **THEN** the route saves an ordered list of model entries reflecting fallback priority

### Requirement: Per-agent provider key override in the console
The agent configuration UI SHALL let an admin set, for a provider used by one of the agent's selected models, an API key that overrides that provider's shared default — scoped to this agent only. Leaving it unset SHALL fall back to the provider's shared key. The entered key SHALL be stored through the per-agent secret mechanism (never displayed in plaintext on reload).

#### Scenario: Set an agent-specific provider key
- **WHEN** an admin enters an override API key for a provider on an agent and saves
- **THEN** the key is stored as that agent's per-agent secret for the provider's `api_key_env`, and is shown masked on reload

#### Scenario: Unset override falls back to shared key
- **WHEN** an admin leaves the per-agent provider key unset
- **THEN** the agent uses the provider's shared default key

