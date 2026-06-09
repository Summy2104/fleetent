# fleetent-apply-api Specification

## Purpose
TBD - created by archiving change 2026-06-02-askit-orchestration-console. Update Purpose after archive.
## Requirements
### Requirement: Idempotent agents apply API
fleetent SHALL expose an idempotent apply API (`POST /admin/agents/apply`, batch `POST /admin/agents/apply:batch`) that upserts a compiled agent definition by `agent_id` (falling back to `name`) into agent_store. askit's fleetent deployer SHALL call this API rather than writing SQLite directly, so fleetent remains the sole writer of its own database. Re-applying the same spec SHALL produce the same result without new side effects beyond audit and version timestamps.

#### Scenario: Apply creates a managed agent
- **WHEN** the deployer sends `POST /admin/agents/apply` with `{"name":"ops-bot","system_prompt":"...","allowed_tools":["shell"],"model":"..."}` and no agent of that name exists
- **THEN** a new agent row is created with `provenance = spec_owned` and the response contains the full snapshot

#### Scenario: Re-apply is idempotent
- **WHEN** the same spec is applied twice in a row
- **THEN** the second apply yields the same agent state with no additional side effects beyond audit and version timestamps

### Requirement: Apply owns the agent definition only, never bindings
The apply API SHALL only own the agent definition: `name` (immutable identity), `system_prompt` / `allowed_tools` / `model` (mutable). Bindings (`user_agents` / `channel_agents` and default bindings) are runtime state and SHALL NOT be overwritten or deleted by apply.

#### Scenario: Apply does not touch bindings
- **WHEN** an existing managed agent has user and channel bindings and a new apply updates its `system_prompt`
- **THEN** the `system_prompt` is updated and all existing `user_agents` / `channel_agents` rows are preserved unchanged

#### Scenario: Immutable name is restored on apply
- **WHEN** an existing managed agent's `name` was changed in the UI and an apply for that agent (matched by `agent_id`) carries the spec `name`
- **THEN** the `name` is force-restored to the spec value

### Requirement: Apply upsert resolution and adopt
The apply API SHALL resolve the target row by `agent_id` first, then by `name`. A same-name match on an ad-hoc (`db_only`) agent SHALL adopt it: reuse the same `agent_id` and flip to `spec_owned` without rebuilding the row.

#### Scenario: Apply adopts a same-name ad-hoc agent
- **WHEN** an ad-hoc agent "tmp-bot" exists and an apply carries name "tmp-bot"
- **THEN** the existing row is adopted (same `agent_id`, flipped to `spec_owned`), not duplicated or rejected

#### Scenario: Apply matched by agent_id updates in place
- **WHEN** an apply carries an `agent_id` of an existing managed agent
- **THEN** the matching row's mutable fields are upserted in place and the `agent_id` is unchanged

### Requirement: Skills delivery triggers hot reload
Managed skills SHALL be delivered to the shared skills directory (not through the agents apply API) and SHALL trigger a hot reload so the skill registry re-scans and picks them up.

#### Scenario: Deployed skill hot reloads
- **WHEN** a managed skill is delivered to the shared skills directory by a fleetent deploy
- **THEN** a hot reload is triggered and the skill registry re-scans, making the skill available without a restart

### Requirement: 无服务端 askit 任务队列,部署唯一经 apply API
系统 **MUST NOT** 维护任何服务端的 askit 任务队列/工作区表(`askit_tasks` / `askit_task_logs` / `askit_workspaces`)。agent 部署 **MUST** 唯一经幂等 apply API 进行(见「Idempotent agents apply API」);askit 部署器只 POST 编译后的 agent 定义,fleetent 仍是其自身数据库的唯一写者。这些任务队列表是 apply-API 模型之前的遗留,已无任何代码使用,**MUST** 被移除。

#### Scenario: schema 中不存在 askit 任务队列表
- **WHEN** 对空库执行 `alembic upgrade head`
- **THEN** 建出的 schema 中不包含 `askit_tasks` / `askit_task_logs` / `askit_workspaces` 表

#### Scenario: 部署仍只经 apply API
- **WHEN** askit 部署器部署一个 agent
- **THEN** 它经 `POST /admin/agents/apply` 提交编译后的定义,过程不依赖任何服务端任务队列表

### Requirement: Apply is authenticated and audited
The apply API SHALL require admin authentication (the deployer uses a service key) and SHALL audit every apply, recording the initiator and the agent affected.

#### Scenario: Unauthenticated apply rejected
- **WHEN** `POST /admin/agents/apply` is sent without valid admin credentials
- **THEN** the response is 401/403 and no agent row is changed

#### Scenario: Apply stamps creator and audits
- **WHEN** admin user `u-admin` initiates a deploy whose apply upserts agent "ops-bot"
- **THEN** the resulting version row records `created_by_user_id = "u-admin"` and an audit entry is written for the apply

