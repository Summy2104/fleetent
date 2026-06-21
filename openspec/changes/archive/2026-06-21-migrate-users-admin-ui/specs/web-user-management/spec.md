## ADDED Requirements

### Requirement: Users managed natively in the React SPA

The React admin SPA SHALL render the users domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list users, create a user, edit profile, set role, block / unblock, reset password, delete a user, and manage IM identities (list, bind, block, restore). Write controls SHALL be admin-only; viewers are read-only.

#### Scenario: List and create users in the SPA

- **WHEN** an admin opens the users view
- **THEN** users are listed via `GET /admin/users`, and creating one calls `POST /admin/users` and refreshes the list

#### Scenario: Role, block, and delete

- **WHEN** an admin changes a user's role, blocks/unblocks, or deletes a user (with confirmation)
- **THEN** the SPA calls the matching endpoint (`PATCH /admin/users/{id}/role`, `POST .../block`|`/unblock`, `DELETE /admin/users/{id}`) and the list reflects the change

#### Scenario: Users no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** users is a native route, not an entry in the legacy deep-link list
