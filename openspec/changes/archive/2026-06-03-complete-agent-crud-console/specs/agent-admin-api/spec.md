## ADDED Requirements

### Requirement: Agent create, read-full, update, and delete endpoints

The system SHALL expose, under role-based Session auth (write requires `admin`/`built_in_admin`, read allows `viewer` and above):

- `POST /admin/agents` with body `{name, system_prompt?, allowed_tools?}` to create a new agent definition. It SHALL persist the def via `agent_store.create_agent` AND create an `agent_admin_state` row with `provenance=adhoc`, `status=enabled` so the agent appears in `GET /admin/agents`. It SHALL return 201 with the new agent's definition, or 409 if the name already exists.
- `GET /admin/agents/{name}` to return the full agent definition resolved from the active version (system_prompt, allowed_tools, and other runtime fields). It SHALL return 404 if the agent does not exist.
- `PATCH /admin/agents/{name}` with a subset of editable fields (`system_prompt`, `allowed_tools`) to edit the agent by creating and activating a new immutable version via `agent_store.create_version` (only provided fields overridden). If the agent's provenance is `managed`, it SHALL mark drift. It SHALL return 200 with the updated definition, or 404 if the agent does not exist.
- `DELETE /admin/agents/{name}` to hard-delete the agent. It SHALL require a confirmation header (`X-Confirm: true`) and SHALL be binding-protected: when the agent is referenced by user/channel bindings the response is 409 and nothing is deleted. Otherwise it SHALL call `agent_store.delete_agent` and remove the `agent_admin_state` row, returning 200.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Create persists def and state row

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","system_prompt":"hi","allowed_tools":["shell"]}`
- **THEN** the response is 201, `agent_store.get_by_name("ops-bot")` returns the def, AND the agent appears in `GET /admin/agents` with provenance `adhoc` and status `enabled`

#### Scenario: Create duplicate name rejected

- **WHEN** an admin posts a create for a name that already exists
- **THEN** the response is 409 and no second agent is created

#### Scenario: Create requires admin

- **WHEN** a `viewer` sends `POST /admin/agents`
- **THEN** the response is 403 and nothing is persisted

#### Scenario: Read full definition

- **WHEN** an authorized user sends `GET /admin/agents/ops-bot`
- **THEN** the response is 200 with the active version's system_prompt and allowed_tools

#### Scenario: Read missing agent

- **WHEN** `GET /admin/agents/nope` targets an agent that does not exist
- **THEN** the response is 404

#### Scenario: Update creates a new active version

- **WHEN** an admin sends `PATCH /admin/agents/ops-bot` with `{"system_prompt":"v2"}`
- **THEN** the response is 200, a new `agent_versions` row is created and activated, and `agent_store.get_by_name("ops-bot").system_prompt == "v2"`

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
