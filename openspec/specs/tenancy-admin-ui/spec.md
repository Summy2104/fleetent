# tenancy-admin-ui Specification

## Purpose
TBD - created by archiving change add-tenancy-admin-ui. Update Purpose after archive.
## Requirements
### Requirement: Tenancy managed natively in the React SPA

The React admin SPA SHALL provide a native Tenancy domain backed by the existing `/admin/tenancy` API: list and create tenants, list and create teams, assign a user to a tenant, and set approvers. Write actions SHALL be admin-only; viewers are read-only.

#### Scenario: List and create tenants and teams

- **WHEN** an admin opens the Tenancy view and creates a tenant or team
- **THEN** tenants/teams are listed via `GET /admin/tenancy/tenants` / `GET /admin/tenancy/teams`, and creation calls `POST /admin/tenancy/tenants` / `POST /admin/tenancy/teams`, refreshing the list

#### Scenario: Assign a user to a tenant

- **WHEN** an admin assigns a user to a tenant
- **THEN** the SPA calls `POST /admin/tenancy/users/{id}/tenant` and the assignment takes effect

#### Scenario: Set an approver

- **WHEN** an admin sets the approver for a tenant or team
- **THEN** the SPA calls `PATCH /admin/tenancy/approvers/{entity_id}` and reflects the change

