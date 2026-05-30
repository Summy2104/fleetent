## ADDED Requirements

### Requirement: Admin role flag on users
The `users` table SHALL have an `is_admin` integer column defaulting to `0`. Routes under `/admin/*` SHALL require the authenticated user's `is_admin` to be `1`.

#### Scenario: Non-admin blocked from admin route
- **WHEN** a user with `is_admin=0` sends `GET /admin/agents` with a valid Bearer token
- **THEN** the response is 403 Forbidden

#### Scenario: Admin allowed
- **WHEN** a user with `is_admin=1` sends `GET /admin/agents`
- **THEN** the response is 200 with the agent list

#### Scenario: Promote and revoke via CLI
- **WHEN** `fleetent-admin promote-admin --user-id <id>` is run
- **THEN** the user's `is_admin` becomes 1
- **AND** `fleetent-admin revoke-admin --user-id <id>` resets it to 0

### Requirement: Agent CRUD endpoints
The system SHALL expose REST endpoints for agent lifecycle.

#### Scenario: POST creates agent and v1
- **WHEN** an admin sends `POST /admin/agents` with body `{"name":"x","system_prompt":"...","allowed_tools":["shell"]}`
- **THEN** the response is 201, an agent row and an `agent_versions` row with version 1 are inserted, `active_version_id` is set, and the body contains the full snapshot

#### Scenario: Duplicate name rejected
- **WHEN** `POST /admin/agents` is sent with a name that already exists (and is not soft-deleted)
- **THEN** the response is 409 Conflict

#### Scenario: GET list returns active versions
- **WHEN** an admin sends `GET /admin/agents`
- **THEN** the response is a JSON array, each element containing the agent's name + active version fields, excluding soft-deleted by default

#### Scenario: GET by name returns active snapshot
- **WHEN** an admin sends `GET /admin/agents/{name}`
- **THEN** the response body contains the active version's `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`, plus `version` and `version_id`

#### Scenario: GET on missing returns 404
- **WHEN** the agent does not exist or is soft-deleted
- **THEN** the response is 404

#### Scenario: DELETE soft-deletes
- **WHEN** an admin sends `DELETE /admin/agents/{name}` for an existing agent
- **THEN** the response is 204 and the agent's `deleted_at` is set; subsequent `GET /admin/agents/{name}` returns 404

### Requirement: Version management endpoints
The system SHALL expose endpoints for listing and activating versions.

#### Scenario: PATCH creates a new version
- **WHEN** an admin sends `PATCH /admin/agents/{name}` with partial fields
- **THEN** a new `agent_versions` row is inserted carrying over unspecified fields from the current active version; the response body returns the new version metadata
- **AND** by default `active_version_id` is updated to the new version unless the request body includes `"activate": false`

#### Scenario: PATCH with activate=false
- **WHEN** the request body sets `"activate": false`
- **THEN** the new version is created but `active_version_id` is unchanged

#### Scenario: List versions
- **WHEN** an admin sends `GET /admin/agents/{name}/versions`
- **THEN** the response is a JSON array of versions sorted by `version` descending, each entry containing `version`, `created_at`, `created_by_user_id`, and a boolean `is_active`

#### Scenario: Activate (rollback)
- **WHEN** an admin sends `POST /admin/agents/{name}/versions/{version}/activate`
- **THEN** the response is 200 and `active_version_id` references that version
- **AND** a request for a non-existent version returns 404

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind users and channels.

#### Scenario: Bind user
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/users` with body `{"user_id":"u1"}`
- **THEN** a row is inserted into `user_agents` and the response is 201

#### Scenario: Unbind user
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** the matching `user_agents` row is removed and the response is 204

#### Scenario: Bind channel records active version
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/channels` with `{"platform":"slack","channel_id":"C1"}`
- **THEN** a row is upserted into `channel_agents` with `bound_version_id` set to the agent's current active version, and the response is 201

#### Scenario: Unbind channel
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/channels/{platform}/{channel_id}`
- **THEN** the row is removed and the response is 204

### Requirement: All admin write operations are audited via created_by_user_id
For every new `agent_versions` row created through the HTTP API, `created_by_user_id` SHALL be set to the authenticated admin's user id.

#### Scenario: PATCH stamps creator
- **WHEN** admin user `u-admin` calls `PATCH /admin/agents/x`
- **THEN** the new `agent_versions` row has `created_by_user_id = "u-admin"`

#### Scenario: CLI does not require admin and leaves creator null
- **WHEN** `fleetent-admin update-agent --name x ...` is run
- **THEN** the new version row's `created_by_user_id` is `NULL`
