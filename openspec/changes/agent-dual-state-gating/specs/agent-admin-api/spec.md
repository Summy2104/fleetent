# agent-admin-api Specification (delta)

## ADDED Requirements

### Requirement: Agent list and detail surface runtime and placement state

`GET /admin/agents`（列表）与 `GET /admin/agents/{name}`（详情）SHALL 在原有期望态字段（`status` / `provenance` 等）基础上，附带每个 agent 的**运行态**与**绑定**投影，且 SHALL NOT 破坏任何既有字段：

- `runtime`：来自 `node_agent_status`（经只读 seam `get_agent_runtime` / `list_agent_runtimes`，接线 `node_store`）。有上报行时为对象 `{phase, health, pid, node_id, reported_at}`；无上报行时为 `null`。
- `placement`：来自 `agent_placements`（经只读 seam `get_agent_placement` / `list_agent_placements`，接线 `placement_store`）。已 pin 时为对象 `{node_id, pinned_at, pinned_by}`；未 pin 时为 `null`。

运行态是**只读投影**（控制真相在 node），platform 不据其做控制决策。列表 SHALL 用批量读取按 `agent_id` 合并，避免逐行 N+1。

#### Scenario: 列表附带运行态与绑定
- **WHEN** 某 agent 已 pin 到 node 且 node 上报其 `phase=running`、`pid`、`health`，管理员请求 `GET /admin/agents`
- **THEN** 该 agent 行含 `runtime={phase:"running", health, pid, node_id, reported_at}` 与 `placement={node_id, ...}`
- **AND** 既有字段 `status` / `provenance` / `agent_name` 不变

#### Scenario: 未上报未绑定的 agent 投影为 null
- **WHEN** 某 agent 既无 `node_agent_status` 行也无 `agent_placements` 行，管理员请求列表或详情
- **THEN** 该 agent 的 `runtime` 为 `null`、`placement` 为 `null`

#### Scenario: 详情附带运行态与绑定
- **WHEN** 管理员请求 `GET /admin/agents/{name}`
- **THEN** 响应在既有 def 字段之外含 `runtime` 与 `placement`（按上述形态，无对应行为 `null`）

## MODIFIED Requirements

### Requirement: Agent create, read-full, update, and delete endpoints

The system SHALL expose, under role-based Session auth (write requires `admin`/`built_in_admin`, read allows `viewer` and above):

- `POST /admin/agents` with body `{name, system_prompt?, allowed_tools?, skills_dir?, mcp_server_ids?, model_overrides?, memory_namespace?}` to create a new agent definition. It SHALL persist the def via `agent_store.create_agent` (passing through the optional version-config fields when provided) AND create an `agent_admin_state` row with `provenance=adhoc`, **`status=disabled`**（新建默认关闭，避免「enabled 但未绑定 node、不会被任何 node 拉起」的误导态；管理员须显式 enable 才进入 node 期望态拉取） so the agent appears in `GET /admin/agents`. It SHALL return 201 with the new agent's definition, or 409 if the name already exists.
- `GET /admin/agents/{name}` to return the full agent definition resolved from the active version, including `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, and `memory_namespace`. It SHALL return 404 if the agent does not exist.
- `PATCH /admin/agents/{name}` with a subset of editable fields (`system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`) to edit the agent by creating and activating a new immutable version via `agent_store.create_version` (only provided fields overridden; omitted fields inherit the prior active version). If the agent's provenance is `managed`, it SHALL mark drift. It SHALL return 200 with the updated definition, or 404 if the agent does not exist.
- `DELETE /admin/agents/{name}` to hard-delete the agent. It SHALL require a confirmation header (`X-Confirm: true`) and SHALL be binding-protected: when the agent is referenced by user bindings the response is 409 and nothing is deleted. Otherwise it SHALL call `agent_store.delete_agent` and remove the `agent_admin_state` row, returning 200.

Every write SHALL emit an `audit_log` entry stamped with the acting user id.

#### Scenario: Create persists def and state row

- **WHEN** an admin sends `POST /admin/agents` with `{"name":"ops-bot","system_prompt":"hi","allowed_tools":["shell"]}`
- **THEN** the response is 201, `agent_store.get_by_name("ops-bot")` returns the def, AND the agent appears in `GET /admin/agents` with provenance `adhoc` and **status `disabled`**

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

### Requirement: Agent lifecycle, clone, template, and observability endpoints

The system SHALL expose, in addition to the existing CRUD/version/binding endpoints:
- `POST /admin/agents/{name}/enable` and `POST /admin/agents/{name}/disable` to toggle `status`. **`enable` SHALL be gated on node placement**: when the agent is not pinned to any node (`placement_store.get_for_agent` is `None`, read via the `get_agent_placement` seam), `enable` SHALL be rejected with `409` and detail `agent not bound to a node`, the agent's `status` SHALL be unchanged, and no `agent.enable` audit entry SHALL be written. `disable` SHALL NOT be gated (disabling is always allowed).
- `POST /admin/agents/{name}/archive` (binding-protected, requires confirmation) and `POST /admin/agents/{name}/restore`.
- `POST /admin/agents/{name}/clone` to create a copy without bindings; the cloned agent SHALL be created with `provenance=adhoc` and **`status=disabled`**（与 create 一致，克隆体未绑定 node，默认关闭）.
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
- **WHEN** an admin sends `POST /admin/agents/ops-bot/clone` with `{"name":"ops-bot-staging"}`
- **THEN** the response is 201 with the new agent's snapshot, the new agent has no bindings, **its `status` is `disabled`**, and an `agent.clone` audit entry is written

#### Scenario: Template list endpoint
- **WHEN** an admin sends `GET /admin/agent-templates`
- **THEN** the response lists the built-in templates with id, display name, allowed_tools, and system_prompt preview

#### Scenario: Observability endpoint aggregates by agent
- **WHEN** an admin or viewer sends `GET /admin/agents/ops-bot/observability`
- **THEN** the response contains the per-agent aggregated metrics and recent-session list
