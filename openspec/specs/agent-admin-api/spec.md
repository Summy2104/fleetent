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


### Requirement: Agent create, read-full, update, and delete endpoints

The system SHALL expose, under role-based Session auth (write requires `admin`/`built_in_admin`, read allows `viewer` and above):

- `POST /admin/agents` with body `{name, system_prompt?, allowed_tools?, skills_dir?, mcp_server_ids?, model_overrides?, memory_namespace?}` to create a new agent definition. It SHALL persist the def via `agent_store.create_agent` (passing through the optional version-config fields when provided) AND create an `agent_admin_state` row with `provenance=adhoc`, `status=enabled` so the agent appears in `GET /admin/agents`. It SHALL return 201 with the new agent's definition, or 409 if the name already exists.
- `GET /admin/agents/{name}` to return the full agent definition resolved from the active version, including `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`. It SHALL return 404 if the agent does not exist.
- `PATCH /admin/agents/{name}` with a subset of editable fields (`system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`) to edit the agent by creating and activating a new immutable version via `agent_store.create_version` (only provided fields overridden; omitted fields inherit the prior active version). If the agent's provenance is `managed`, it SHALL mark drift. It SHALL return 200 with the updated definition, or 404 if the agent does not exist.
- `DELETE /admin/agents/{name}` to hard-delete the agent. It SHALL require a confirmation header (`X-Confirm: true`) and SHALL be binding-protected: when the agent is referenced by user/channel bindings the response is 409 and nothing is deleted. Otherwise it SHALL call `agent_store.delete_agent` and remove the `agent_admin_state` row, returning 200.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Create persists def and state row

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","system_prompt":"hi","allowed_tools":["shell"]}`
- **THEN** the response is 201, `agent_store.get_by_name("ops-bot")` returns the def, AND the agent appears in `GET /admin/agents` with provenance `adhoc` and status `enabled`

#### Scenario: Create persists version-config fields

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","skills_dir":"/s","mcp_server_ids":["github"],"model_overrides":{"model":"x"},"memory_namespace":"team"}`
- **THEN** the response is 201 and `agent_store.get_by_name("ops-bot")` returns those four fields on the active version

#### Scenario: Create duplicate name rejected

- **WHEN** an admin posts a create for a name that already exists
- **THEN** the response is 409 and no second agent is created

#### Scenario: Create requires admin

- **WHEN** a `viewer` sends `POST /admin/agents`
- **THEN** the response is 403 and nothing is persisted

#### Scenario: Read full definition

- **WHEN** an authorized user sends `GET /admin/agents/ops-bot`
- **THEN** the response is 200 with the active version's `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`

#### Scenario: Read missing agent

- **WHEN** `GET /admin/agents/nope` targets an agent that does not exist
- **THEN** the response is 404

#### Scenario: Update creates a new active version

- **WHEN** an admin sends `PATCH /admin/agents/ops-bot` with `{"system_prompt":"v2"}`
- **THEN** the response is 200, a new `agent_versions` row is created and activated, and `agent_store.get_by_name("ops-bot").system_prompt == "v2"`

#### Scenario: Update overrides only provided version-config fields

- **WHEN** an admin sends `PATCH /admin/agents/ops-bot` with `{"memory_namespace":"team"}` and the prior version had `skills_dir="/s"`
- **THEN** the new active version has `memory_namespace == "team"` and still has `skills_dir == "/s"`

#### Scenario: Update of managed agent marks drift

- **WHEN** an admin edits an agent whose provenance is `managed`
- **THEN** the agent's `drift` flag is set

#### Scenario: Delete blocked by bindings

- **WHEN** an admin sends `DELETE /admin/agents/ops-bot` with `X-Confirm: true` while bindings reference "ops-bot"
- **THEN** the response is 409 and the agent is not deleted

#### Scenario: Delete requires confirmation

- **WHEN** a delete request lacks `X-Confirm: true`
- **THEN** the response is 428 and nothing is deleted

#### Scenario: Delete removes agent and state

- **WHEN** an admin sends `DELETE /admin/agents/ops-bot` with `X-Confirm: true` and no bindings reference it
- **THEN** the response is 200, `agent_store.get_by_name("ops-bot")` is `None`, and the agent no longer appears in `GET /admin/agents`

### Requirement: Console and apply seams wired to the store

The agent console and apply API seams (`get_agent_def`, `create_agent_def`, `update_agent_def`) SHALL be wired in `server.py` to the corresponding `agent_store` operations, so clone, create-from-template, and apply persist real definitions in production rather than acting as inert stubs.

#### Scenario: Clone persists via wired seam

- **WHEN** the server is configured and an admin sends `POST /admin/agents/{name}/clone`
- **THEN** the clone reads the source via the wired `get_agent_def` and writes the copy via the wired `create_agent_def`, and `agent_store.get_by_name(new_name)` returns the copy

#### Scenario: Apply persists via wired seams

- **WHEN** an admin sends `POST /admin/agents/apply` for a new spec
- **THEN** the wired `create_agent_def` persists it and `agent_store.get_by_name(spec.name)` returns the def


### Requirement: Agent template management endpoints

The system SHALL expose template CRUD endpoints under role-based Session auth (write requires `admin`/`built_in_admin`, read allows `viewer` and above), reading and writing through `agent_template_store`:

- `GET /admin/agent-templates` lists templates from the store (id, display_name, allowed_tools, system_prompt).
- `POST /admin/agent-templates` with body `{id, display_name, allowed_tools?, system_prompt?}` creates a template; 201 with the template, or 409 if the id already exists.
- `PATCH /admin/agent-templates/{id}` with a subset of `display_name`/`allowed_tools`/`system_prompt` edits a template; 200 with the updated template, or 404 if it does not exist.
- `DELETE /admin/agent-templates/{id}` removes a template; 200 if removed, or 404 if it does not exist.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Create template

- **WHEN** an admin sends `POST /admin/agent-templates` with `{"id":"triage","display_name":"Triage","allowed_tools":["read_*"],"system_prompt":"You triage."}`
- **THEN** the response is 201 and `GET /admin/agent-templates` includes `triage`

#### Scenario: Create duplicate id rejected

- **WHEN** an admin posts a create for an id that already exists
- **THEN** the response is 409 and no second template is created

#### Scenario: Edit template

- **WHEN** an admin sends `PATCH /admin/agent-templates/ops` with `{"system_prompt":"v2"}`
- **THEN** the response is 200 and the template's `system_prompt` is `v2` while `allowed_tools` is unchanged

#### Scenario: Edit missing template

- **WHEN** a PATCH targets an id that does not exist
- **THEN** the response is 404

#### Scenario: Delete template

- **WHEN** an admin sends `DELETE /admin/agent-templates/support`
- **THEN** the response is 200 and `GET /admin/agent-templates` no longer includes `support`

#### Scenario: Delete missing template

- **WHEN** a DELETE targets an id that does not exist
- **THEN** the response is 404

#### Scenario: Viewer blocked from template write

- **WHEN** a `viewer` sends a create/edit/delete request to `/admin/agent-templates`
- **THEN** the response is 403 and nothing is persisted

### Requirement: Agent creation requires an existing template
`POST /admin/agents` SHALL require a `template_id` naming an existing agent template. A request missing `template_id` SHALL be rejected with 422; a request naming a template that does not exist SHALL be rejected with 404. On success the created agent's version snapshot SHALL persist the `template_id`, and `GET /admin/agents/{name}` SHALL include `template_id` in its response. Editing an agent (`PATCH /admin/agents/{name}`) SHALL NOT require `template_id`.

#### Scenario: Create without template_id rejected
- **WHEN** an admin sends `POST /admin/agents` with a body omitting `template_id`
- **THEN** the response is 422 and no agent is created

#### Scenario: Create with unknown template_id rejected
- **WHEN** an admin sends `POST /admin/agents` with `template_id` that matches no existing template
- **THEN** the response is 404 and no agent is created

#### Scenario: Create with valid template persists the link
- **WHEN** an admin sends `POST /admin/agents` with a `template_id` of an existing template
- **THEN** the response is 201
- **AND** `GET /admin/agents/{name}` returns `template_id` equal to that template
