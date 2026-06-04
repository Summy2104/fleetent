## ADDED Requirements

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
