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

### Requirement: Role-based guard for agent lifecycle and console writes

The lifecycle, clone, create-from-template, and observability endpoints under `/admin/agents/*` SHALL apply the same role-based Session auth required for the version and binding endpoints: write operations (create, edit, clone, create-from-template, enable, disable, archive, restore, model change, binding) SHALL require `role in {admin, built_in_admin}`; read operations (list, detail, observability) SHALL be allowed for `viewer` and above. No `users.is_admin` column SHALL be introduced; the compatibility mapping `is_admin == role in {admin, built_in_admin}` (provided by `2026-05-30-user-management`) SHALL hold.

#### Scenario: Viewer blocked from agent write
- **WHEN** a `viewer` sends a create/edit/toggle/archive/clone request to `/admin/agents/*`
- **THEN** the response is 403 and nothing is persisted

#### Scenario: Viewer allowed to read list and observability
- **WHEN** a `viewer` sends `GET /admin/agents` or `GET /admin/agents/{name}/observability`
- **THEN** the response is 200 with the data

#### Scenario: Admin allowed to manage
- **WHEN** an `admin` or `built_in_admin` sends a write request to `/admin/agents/*`
- **THEN** the request is authorized (subject to other validation)

### Requirement: Agent lifecycle, clone, template, and observability endpoints

The system SHALL expose, in addition to the existing CRUD/version/binding endpoints:
- `POST /admin/agents/{name}/enable` and `POST /admin/agents/{name}/disable` to toggle `status`.
- `POST /admin/agents/{name}/archive` (binding-protected, requires confirmation) and `POST /admin/agents/{name}/restore`.
- `POST /admin/agents/{name}/clone` to create a copy without bindings.
- `GET /admin/agent-templates` and create-from-template support.
- `GET /admin/agents/{name}/observability` for the per-agent aggregated view.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Disable endpoint stops routing
- **WHEN** an admin sends `POST /admin/agents/ops-bot/disable`
- **THEN** the response is 200, `status` becomes `disabled`, and a subsequent `/chat` routing to "ops-bot" is rejected with "该 Agent 已停用"
- **AND** an `agent.disable` audit entry is written

#### Scenario: Archive endpoint enforces binding protection
- **WHEN** an admin sends `POST /admin/agents/ops-bot/archive` while "ops-bot" is bound or default
- **THEN** the response is 409 with the occupying users/channels/default flag and `status` is unchanged

#### Scenario: Archive endpoint requires confirmation
- **WHEN** an archive request lacks the confirmation flag
- **THEN** the response indicates confirmation is required and no state change occurs

#### Scenario: Clone endpoint excludes bindings
- **WHEN** an admin sends `POST /admin/agents/ops-bot/clone` with `{"name":"ops-bot-staging"}`
- **THEN** the response is 201 with the new agent's snapshot, the new agent has no bindings, and an `agent.clone` audit entry is written

#### Scenario: Template list endpoint
- **WHEN** an admin sends `GET /admin/agent-templates`
- **THEN** the response lists the built-in templates with id, display name, allowed_tools, and system_prompt preview

#### Scenario: Observability endpoint aggregates by agent
- **WHEN** an admin or viewer sends `GET /admin/agents/ops-bot/observability`
- **THEN** the response contains the per-agent aggregated metrics and recent-session list

