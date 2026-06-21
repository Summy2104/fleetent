## ADDED Requirements

### Requirement: OAuth connectors managed natively in the React SPA

The React admin SPA SHALL render OAuth external-service connectors natively (not a deep-link to legacy) and SHALL support the full lifecycle against the existing admin API: list, create, **edit**, **delete**, **test**, view lifecycle and agent bindings, manage the authorization matrix (grants, revoke, offboarding), and write credentials. This closes the legacy create-only gap. No credential value SHALL be displayed in plaintext.

#### Scenario: Edit, delete, and test a connector

- **WHEN** an admin edits an existing OAuth connector and saves, deletes one (with confirmation), or tests one
- **THEN** the SPA calls `PUT /admin/connectors/{id}` / `DELETE /admin/connectors/{id}` / `POST /admin/connectors/{id}/test` and reflects the result

#### Scenario: Authorization matrix and revoke

- **WHEN** an admin views grants and revokes a user's grant
- **THEN** the SPA calls `GET /admin/connectors/grants` and `POST /admin/connectors/grants/{user}/{connector}/revoke`, refreshing the matrix

#### Scenario: Connectors no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Connectors is a native route, not an entry in the legacy deep-link list
