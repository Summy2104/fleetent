# agent-admin-api Specification

## Purpose
TBD - created by archiving change 2026-05-29-multi-agent-management. Update Purpose after archive.
## Requirements
### Requirement: Version and binding endpoints reuse role-based Session auth
The new `/admin/agents/*` binding endpoints SHALL authenticate via the existing Session scheme (`Authorization: Session <token>`, validated by `auth.validate_session`) and authorize via the `role` system: read endpoints allow `viewer`/`admin`/`built_in_admin`; write endpoints require `admin`/`built_in_admin`. They SHALL NOT introduce a `users.is_admin` column. Agent creation/update/lifecycle continues to be served by the existing `agent_console_api` surfaces; this capability only adds binding endpoints.

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to a `/admin/agents/*` binding endpoint carries no valid Session token
- **THEN** the response is 401

#### Scenario: Viewer can read but not write
- **WHEN** a `viewer` calls `GET /admin/agents/{name}/bindings`
- **THEN** the response is 200
- **AND WHEN** the same `viewer` calls `POST /admin/agents/{name}/bindings/users`
- **THEN** the response is 403

#### Scenario: Admin can write
- **WHEN** an `admin` calls `POST /admin/agents/{name}/bindings/users` with body `{"user_id":"u1"}` for an existing agent
- **THEN** the response is 201 and the binding is persisted

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind **users** to/from an agent, to bind and unbind **IM groups** (`platform` + `group_id`) for an agent, and to set the agent's **IM capability** flags (`supports_dm` / `supports_groups`), all requiring `admin`/`built_in_admin`. （Channel-routing 绑定已于阶段 1 移除；群白名单是访问控制、非路由——见 im-access-model。运行时强制属阶段 3。）

#### Scenario: Bind user
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/users` with body `{"user_id":"u1"}`
- **THEN** a row is inserted into `user_agents` and the response is 201

#### Scenario: Unbind user
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** the matching `user_agents` row is removed and the response is 204

#### Scenario: Bind IM group
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/groups` with body `{"platform":"slack","group_id":"C0123"}`
- **THEN** a row is inserted into `agent_im_groups` keyed `(agent_id, "slack", "C0123")` and the response is 201

#### Scenario: Unbind IM group
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/groups/{platform}/{group_id}`
- **THEN** the matching `agent_im_groups` row is removed and the response is 204

#### Scenario: Set IM capability
- **WHEN** an admin sets the agent's `supports_dm` / `supports_groups`
- **THEN** the corresponding `agents` columns are updated and the response is 200

#### Scenario: Bind to missing agent
- **WHEN** a binding/capability endpoint targets an agent name that does not exist
- **THEN** the response is 404

#### Scenario: Viewer cannot configure
- **WHEN** a `viewer` calls any user/group binding or capability write endpoint
- **THEN** the response is 403

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

The system SHALL expose, in addition to the existing CRUD/binding endpoints:
- `POST /admin/agents/{name}/enable` and `POST /admin/agents/{name}/disable` to toggle `status`. **`enable` SHALL be gated on node placement**: when the agent is not pinned to any node (`placement_store.get_for_agent` is `None`), `enable` SHALL be rejected with `409` and detail `agent not bound to a node`, the agent's `status` SHALL be unchanged, and no `agent.enable` audit entry SHALL be written. `disable` SHALL NOT be gated (disabling is always allowed).
- `POST /admin/agents/{name}/archive` (binding-protected, requires confirmation) and `POST /admin/agents/{name}/restore`.
- `POST /admin/agents/{name}/clone` to create a copy without bindings; the cloned agent SHALL be created with `status=disabled`.
- `GET /admin/agent-templates` and create-from-template support.
- `GET /admin/agents/{name}/observability` for the per-agent aggregated view.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Enable rejected when not bound to a node
- **WHEN** an admin sends `POST /admin/agents/ops-bot/enable` while "ops-bot" has no `agent_placements` row
- **THEN** the response is 409 with detail `agent not bound to a node`, `status` is unchanged, and no `agent.enable` audit entry is written

#### Scenario: Enable succeeds once bound to a node
- **WHEN** "ops-bot" is pinned to a node and an admin sends `POST /admin/agents/ops-bot/enable`
- **THEN** the response is 200, `status` becomes `enabled`, and an `agent.enable` audit entry is written

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
- **WHEN** an admin sends `POST /admin/agents/ops-bot/clone` with `{"new_name":"ops-bot-staging"}`
- **THEN** the response is 200 with the clone summary, the new agent has no bindings, its `status` is `disabled`, and an `agent.clone` audit entry is written

#### Scenario: Template list endpoint
- **WHEN** an admin sends `GET /admin/agent-templates`
- **THEN** the response lists the built-in templates with id, display name, allowed_tools, and system_prompt preview

#### Scenario: Observability endpoint aggregates by agent
- **WHEN** an admin or viewer sends `GET /admin/agents/ops-bot/observability`
- **THEN** the response contains the per-agent aggregated metrics and recent-session list

### Requirement: Agent create, read-full, update, and delete endpoints

The system SHALL expose, under role-based Session auth (write requires `admin`/`built_in_admin`, read allows `viewer` and above):

- `POST /admin/agents` with body `{name, system_prompt?, allowed_tools?, skills_dir?, mcp_server_ids?, model_overrides?, memory_namespace?}` to create a new agent definition. It SHALL persist the def via `agent_store.create_agent` (writing the optional config fields when provided onto the `agents` row) AND create an `agent_admin_state` row with `status=disabled`（新建默认关闭,避免「enabled 但未绑定 node、不会被任何 node 拉起」的误导态;管理员须显式 enable 才进入 node 期望态拉取）so the agent appears in `GET /admin/agents`. It SHALL return 201 with the new agent's definition, or 409 if the name already exists.
- `GET /admin/agents/{name}` to return the full agent definition resolved directly from the `agents` row, including `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`. It SHALL return 404 if the agent does not exist.
- `PATCH /admin/agents/{name}` with a subset of editable fields (`system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`) to edit the agent **in place via the single config-update choke point** (only provided fields overridden; omitted fields retain their prior value). No new version is created and no version pointer is changed. It SHALL return 200 with the updated definition, or 404 if the agent does not exist.
- `DELETE /admin/agents/{name}` to hard-delete the agent. It SHALL require a confirmation header (`X-Confirm: true`) and SHALL be binding-protected: when the agent is referenced by user bindings the response is 409 and nothing is deleted. Otherwise it SHALL call `agent_store.delete_agent` and remove the `agent_admin_state` row, returning 200.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Create persists def and state row

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","system_prompt":"hi","allowed_tools":["shell"]}`
- **THEN** the response is 201, `agent_store.get_by_name("ops-bot")` returns the def, AND the agent appears in `GET /admin/agents` with status `disabled`

#### Scenario: Create persists config fields

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","skills_dir":"/s","mcp_server_ids":["github"],"model_overrides":{"model":"x"},"memory_namespace":"team"}`
- **THEN** the response is 201 and `agent_store.get_by_name("ops-bot")` returns those four fields on the agent's row

#### Scenario: Create duplicate name rejected

- **WHEN** an admin posts a create for a name that already exists
- **THEN** the response is 409 and no second agent is created

#### Scenario: Create requires admin

- **WHEN** a `viewer` sends `POST /admin/agents`
- **THEN** the response is 403 and nothing is persisted

#### Scenario: Read full definition

- **WHEN** an authorized user sends `GET /admin/agents/ops-bot`
- **THEN** the response is 200 with the agent row's `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`

#### Scenario: Read missing agent

- **WHEN** `GET /admin/agents/nope` targets an agent that does not exist
- **THEN** the response is 404

#### Scenario: Update edits the agent in place

- **WHEN** an admin sends `PATCH /admin/agents/ops-bot` with `{"system_prompt":"v2"}`
- **THEN** the response is 200, the `agents` row is updated in place (no new version row, no version pointer change), and `agent_store.get_by_name("ops-bot").system_prompt == "v2"`

#### Scenario: Update overrides only provided config fields

- **WHEN** an admin sends `PATCH /admin/agents/ops-bot` with `{"memory_namespace":"team"}` and the agent previously had `skills_dir="/s"`
- **THEN** the updated `agents` row has `memory_namespace == "team"` and still has `skills_dir == "/s"`

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

The agent console seams (`get_agent_def`, `create_agent_def`, `update_agent_def`) SHALL be wired in `server.py` to the corresponding `agent_store` operations, so clone and create-from-template persist real definitions in production rather than acting as inert stubs.

#### Scenario: Clone persists via wired seam

- **WHEN** the server is configured and an admin sends `POST /admin/agents/{name}/clone`
- **THEN** the clone reads the source via the wired `get_agent_def` and writes the copy via the wired `create_agent_def`, and `agent_store.get_by_name(new_name)` returns the copy

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
`POST /admin/agents` SHALL require a `template_id` naming an existing agent template. A request missing `template_id` SHALL be rejected with 422; a request naming a template that does not exist SHALL be rejected with 404. On success the created agent definition SHALL persist the `template_id` on its `agents` row, and `GET /admin/agents/{name}` SHALL include `template_id` in its response. Editing an agent (`PATCH /admin/agents/{name}`) SHALL NOT require `template_id`.

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

### Requirement: Agent binding read endpoint

The agent admin API SHALL expose `GET /admin/agents/{name}/bindings` returning the
agent's current bindings: bound user ids and bound MCP `server_id`s. Reads SHALL be
allowed for viewer and admin roles.

#### Scenario: Read an agent's bindings

- **WHEN** an admin or viewer sends `GET /admin/agents/{name}/bindings`
- **THEN** the response contains `users` and `mcp_servers` for that agent

#### Scenario: Unknown agent

- **WHEN** the agent name does not exist
- **THEN** the endpoint responds 404

### Requirement: Agent MCP binding endpoints

The agent admin API SHALL expose `POST /admin/agents/{name}/bindings/mcp/{server_id}`
and `DELETE /admin/agents/{name}/bindings/mcp/{server_id}` to bind and unbind an MCP
server for an agent. Writes SHALL require admin role and SHALL be audited. The POST
SHALL reject an unknown `server_id` (not present in `GET /admin/mcp/servers`) with 404.

#### Scenario: Bind a known MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/bindings/mcp/github` and "github" is a known server
- **THEN** the binding is recorded and the action is audited

#### Scenario: Bind an unknown MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/bindings/mcp/nope` and "nope" is not a known server
- **THEN** the endpoint responds 404 and no binding is recorded

#### Scenario: Viewer cannot bind

- **WHEN** a viewer attempts the POST or DELETE MCP binding route
- **THEN** the request is rejected as forbidden

### Requirement: Agent knowledge-base binding endpoints
The agent admin API SHALL expose agent-side endpoints to manage an agent's knowledge-base bindings over the existing `agent_kbs` store, so the agent console can list and edit them without going through the KB module. Reads SHALL allow viewer or admin; writes SHALL require admin. The endpoints resolve the agent by name to its id and operate within the agent's tenant.

#### Scenario: List an agent's knowledge bases
- **WHEN** a viewer or admin calls `GET /admin/agents/{name}/kbs`
- **THEN** the response lists the kb_ids bound to that agent

#### Scenario: Bind a knowledge base to an agent
- **WHEN** an admin calls `POST /admin/agents/{name}/kbs` with a `kb_id`
- **THEN** the binding is created (idempotently) via the `agent_kbs` store and the kb_id appears in the agent's bound list

#### Scenario: Unbind a knowledge base from an agent
- **WHEN** an admin calls `DELETE /admin/agents/{name}/kbs/{kb_id}`
- **THEN** the binding is removed and the kb_id no longer appears in the agent's bound list

#### Scenario: Viewer cannot mutate KB bindings
- **WHEN** a viewer calls the bind or unbind endpoint
- **THEN** the request is rejected with 403

### Requirement: Agent OAuth connector binding endpoints
The agent admin API SHALL expose agent-side endpoints to manage which external services an agent may use, parallel to the MCP binding endpoints. Reads SHALL allow viewer or admin; writes SHALL require admin. Binding a service that does not exist in the external services registry SHALL be rejected. HTTP 端点路径与路径参数 token 保持不变（向后兼容）。

#### Scenario: List an agent's OAuth connector bindings
- **WHEN** a viewer or admin calls `GET /admin/agents/{name}/bindings/oauth`
- **THEN** the response lists the service ids bound to that agent

#### Scenario: Bind an OAuth connector to an agent
- **WHEN** an admin calls `POST /admin/agents/{name}/bindings/oauth/{connector_id}` for an existing service
- **THEN** the binding is created (idempotently) and the service id appears in the agent's bound list

#### Scenario: Bind rejects unknown connector
- **WHEN** an admin binds a connector_id that is not in the external services registry
- **THEN** the request is rejected with 404

#### Scenario: Unbind an OAuth connector from an agent
- **WHEN** an admin calls `DELETE /admin/agents/{name}/bindings/oauth/{connector_id}`
- **THEN** the binding is removed

#### Scenario: Viewer cannot mutate OAuth bindings
- **WHEN** a viewer calls the bind or unbind endpoint
- **THEN** the request is rejected with 403

### Requirement: Agent list and detail surface runtime and placement state

`GET /admin/agents`（列表）与 `GET /admin/agents/{name}`（详情）SHALL 在原有期望态字段（`status` 等）基础上,附带每个 agent 的**运行态**与**绑定**投影,且 SHALL NOT 破坏任何既有字段:

- `runtime`:来自 `node_agent_status`（经只读 seam `get_agent_runtime` / `list_agent_runtimes`,接线 `node_store`）。有上报行时为对象 `{phase, health, pid, node_id, reported_at}`;无上报行时为 `null`。
- `placement`:来自 `agent_placements`（经只读 seam `get_agent_placement` / `list_agent_placements`,接线 `placement_store`）。已 pin 时为对象 `{node_id, pinned_at, pinned_by}`;未 pin 时为 `null`。

运行态是**只读投影**(控制真相在 node),platform 不据其做控制决策。列表 SHALL 用批量读取按 `agent_id` 合并,避免逐行 N+1。

#### Scenario: 列表附带运行态与绑定
- **WHEN** 某 agent 已 pin 到 node 且 node 上报其 `phase=running`、`pid`、`health`,管理员请求 `GET /admin/agents`
- **THEN** 该 agent 行含 `runtime={phase:"running", health, pid, node_id, reported_at}` 与 `placement={node_id, ...}`
- **AND** 既有字段 `status` / `agent_name` 不变

#### Scenario: 未上报未绑定的 agent 投影为 null
- **WHEN** 某 agent 既无 `node_agent_status` 行也无 `agent_placements` 行,管理员请求列表或详情
- **THEN** 该 agent 的 `runtime` 为 `null`、`placement` 为 `null`

#### Scenario: 详情附带运行态与绑定
- **WHEN** 管理员请求 `GET /admin/agents/{name}`
- **THEN** 响应在既有 def 字段之外含 `runtime` 与 `placement`（按上述形态,无对应行为 `null`）

