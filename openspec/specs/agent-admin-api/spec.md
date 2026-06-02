# agent-admin-api Specification

## Purpose
TBD - created by archiving change 2026-05-29-multi-agent-management. Update Purpose after archive.
## Requirements
### Requirement: Version and binding endpoints reuse role-based Session auth
The new `/admin/agents/*` version and binding endpoints SHALL authenticate via the existing Session scheme (`Authorization: Session <token>`, validated by `auth.validate_session`) and authorize via the `role` system: read endpoints allow `viewer`/`admin`/`built_in_admin`; write endpoints require `admin`/`built_in_admin`. They SHALL NOT introduce a `users.is_admin` column. Agent creation/update/lifecycle continues to be served by the existing `agent_apply_api` (`POST /admin/agents/apply`) and `agent_console_api` surfaces; this capability only adds version and binding endpoints.

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to a `/admin/agents/*` version or binding endpoint carries no valid Session token
- **THEN** the response is 401

#### Scenario: Viewer can read but not write
- **WHEN** a `viewer` calls `GET /admin/agents/{name}/versions`
- **THEN** the response is 200
- **AND WHEN** the same `viewer` calls `POST /admin/agents/{name}/versions/{v}/activate`
- **THEN** the response is 403

#### Scenario: Admin can write
- **WHEN** an `admin` calls `POST /admin/agents/{name}/versions/{v}/activate` for an existing version
- **THEN** the response is 200 and `active_version_id` references that version

### Requirement: Version management endpoints
The system SHALL expose endpoints for listing and activating an agent's versions.

#### Scenario: List versions
- **WHEN** an authorized user sends `GET /admin/agents/{name}/versions`
- **THEN** the response is a JSON array sorted by `version` descending, each entry containing `version`, `version_id`, `created_at`, `created_by_user_id`, and a boolean `is_active`

#### Scenario: List versions for missing agent
- **WHEN** the agent does not exist
- **THEN** the response is 404

#### Scenario: Activate (rollback)
- **WHEN** an admin sends `POST /admin/agents/{name}/versions/{version}/activate`
- **THEN** the response is 200 and `active_version_id` references that version

#### Scenario: Activate non-existent version
- **WHEN** the requested version number does not exist for the agent
- **THEN** the response is 404 and `active_version_id` is unchanged

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind users and channels, requiring `admin`.

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

#### Scenario: Bind to missing agent
- **WHEN** a binding endpoint targets an agent name that does not exist
- **THEN** the response is 404

