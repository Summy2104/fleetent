## ADDED Requirements

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
