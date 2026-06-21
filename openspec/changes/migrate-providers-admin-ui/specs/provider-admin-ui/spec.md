## ADDED Requirements

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
