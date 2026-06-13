## Purpose

Defines agent configurations (system prompt, tool allowlist) stored in SQLite, supports user-to-agent assignment, and controls which tools an agent can access via glob patterns.
## Requirements
### Requirement: Agent definition storage
The system SHALL store agent definitions in the `agents` SQLite table with columns: `id`, `name` (UNIQUE), `system_prompt` (nullable; superseded by `agent_versions`), `allowed_tools` (nullable; superseded by `agent_versions`), `active_version_id` (→ `agent_versions.id`), `created_at`. Per-version mutable fields (system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace) SHALL live in `agent_versions`. Archival/disable is handled by the existing `agent_admin_store` console state, not by a column on `agents`. This storage is the **authoring** source of truth; runtime resolution is file-sourced (see "Runtime agent resolution is file-sourced") and SHALL NOT read these tables.

#### Scenario: Create agent persists agents + agent_versions in one transaction
- **WHEN** admin calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell"]'`
- **THEN** one row is inserted into `agents` AND one row into `agent_versions` (version=1) inside a single transaction; `agents.active_version_id` references the new version row

#### Scenario: Query agent by name is an authoring/console read, not a runtime path
- **WHEN** the admin console or CLI looks up agent name `"assistant"` whose `active_version_id` points to version 3
- **THEN** `agent_store.get_by_name("assistant")` returns a structure whose `system_prompt` and `allowed_tools` come from version 3's `agent_versions` row
- **AND** this DB read serves authoring/console only; runtime message resolution does NOT use it (runtime is file-sourced)

### Requirement: User-to-agent assignment
The system SHALL support assigning one or more agents to a user via the `user_agents` table.

#### Scenario: User assigned via CLI
- **WHEN** admin runs `fleetent-admin assign-user --user-id <id> --agent-name <name>`
- **THEN** a row exists in `user_agents(user_id, agent_id)`

#### Scenario: User unassigned via CLI
- **WHEN** admin runs `fleetent-admin unassign-user --user-id <id> --agent-name <name>`
- **THEN** the matching row in `user_agents` is removed

#### Scenario: Look up user's agent resolves to active snapshot
- **WHEN** a message arrives from `user_id=X` who is bound to agent `agent_id=1`
- **THEN** the system retrieves the active `AgentSnapshot` for `agent_id=1` and applies its system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace

### Requirement: allowed_tools wildcard support
The `allowed_tools` field SHALL support glob-style wildcards for MCP server tools, as before. MCP tool visibility is further constrained by the snapshot's `mcp_server_ids` allowlist; the tool must pass BOTH checks to appear in the schema.

#### Scenario: Wildcard matches all tools from an allowed MCP server
- **WHEN** `allowed_tools = ["github__*"]` AND `mcp_server_ids = ["github"]`
- **THEN** any tool with prefix `github__` passes

#### Scenario: Wildcard allowed but server not whitelisted
- **WHEN** `allowed_tools = ["github__*"]` AND `mcp_server_ids = []`
- **THEN** no `github__*` tool is offered to the LLM

### Requirement: Schema
The `agents` table SHALL store: `id`, `name` (UNIQUE), `system_prompt` (nullable), `allowed_tools` (nullable JSON array text), `active_version_id` (nullable, references `agent_versions(id)`), `created_at`.
The `user_agents` table SHALL store: `user_id` (→ users.id), `agent_id` (→ agents.id), with PRIMARY KEY on `(user_id, agent_id)`.

#### Scenario: Duplicate agent name rejected
- **WHEN** admin tries to create an agent with a name that already exists
- **THEN** the database UNIQUE constraint prevents it and an error is returned

#### Scenario: active_version_id references a version row
- **WHEN** an agent has been created
- **THEN** `agents.active_version_id` is non-null and references a row in `agent_versions` whose `agent_id` matches

### Requirement: Route configuration schema
`RouteConfig` defines the LLM routing parameters for a task type. It SHALL contain: `base_url`, `model`, `api_key_env`, `max_tokens`, and an optional `fallbacks` ordered sequence of model names to try when the primary model is unavailable.

#### Scenario: RouteConfig with fallbacks
- **WHEN** `RouteConfig` is instantiated with `fallbacks=("claude-haiku-4-5",)`
- **THEN** the config holds a valid fallback sequence accessible as `config.fallbacks`

#### Scenario: RouteConfig without fallbacks remains valid
- **WHEN** `RouteConfig` is instantiated without the `fallbacks` parameter
- **THEN** `config.fallbacks` is an empty tuple and the config is fully valid

### Requirement: Agent console state storage

The agent operational state SHALL store `status` (`enabled` / `disabled` / `archived`, default `enabled`), `provenance` (`managed` / `adhoc`, default `adhoc`), and `drift` (integer boolean, default `0`). `status=archived` SHALL be consistent with the soft-delete marker (archive sets both; restore clears the soft-delete marker and sets `status=enabled`). These columns SHALL be provided via an Alembic migration that backfills existing rows (`status=enabled`, or `status=archived` where already soft-deleted; `provenance=adhoc`, `drift=0`). SQL SHALL use named parameters and go through the store boundary; no ORM.

> Implementation note: this state lives in a side table `agent_admin_state` (migration 015, modeled on `skill_admin_state`) keyed by agent name rather than ALTERing the `agents` table; this is the "console state" the agent-definition storage requirement defers archival/disable to.

#### Scenario: New columns added with defaults via migration
- **WHEN** the Alembic migration runs against an existing database
- **THEN** `agent_admin_state` gains `status` / `provenance` / `drift` columns; existing rows get `status=enabled` (or `archived` if already soft-deleted), `provenance=adhoc`, `drift=0`

#### Scenario: Archive keeps status and deleted_at consistent
- **WHEN** an agent is archived
- **THEN** `status` is `archived` AND `deleted_at` is set in the same transaction

#### Scenario: Restore clears soft delete
- **WHEN** an archived agent is restored within retention
- **THEN** `status` becomes `enabled` AND `deleted_at` is cleared

### Requirement: Routing honors agent status

Routing resolution SHALL reject new sessions for agents whose `status` is `disabled` or `archived`. A `disabled` agent SHALL yield a "该 Agent 已停用" rejection (reversible). An `archived` agent SHALL be treated as not routable (equivalent to not existing in the routable list).

> New constraint layered on the existing "soft-deleted agents not returned" behavior.

#### Scenario: Disabled agent not routable
- **WHEN** a message routes to an agent with `status=disabled`
- **THEN** the request is rejected with "该 Agent 已停用" and does not enter agent_loop

#### Scenario: Enabled agent routable
- **WHEN** a message routes to an agent with `status=enabled`
- **THEN** the request proceeds to agent_loop normally

#### Scenario: Archived agent absent from routable list
- **WHEN** the routable agent list is resolved
- **THEN** agents with `status=archived` are excluded

### Requirement: Agent hard deletion

The store SHALL expose `agent_store.delete_agent(name)` that removes the agent, all its versions, and its binding child rows in a single transaction (delete `agent_mcp_server_bindings` and `agent_oauth_bindings` rows, then `agent_versions` rows, then the `agents` row, in FK-safe order). It SHALL return a boolean: `True` when a row was deleted, `False` when no agent with that name exists. SQL SHALL use named parameters and go through the store boundary; no ORM.

#### Scenario: Delete removes agents and agent_versions rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an existing agent with N versions
- **THEN** the `agents` row and all N `agent_versions` rows are removed in one transaction AND the call returns `True`

#### Scenario: Delete cleans binding child rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an agent holding MCP server bindings and OAuth bindings
- **THEN** the `agent_mcp_server_bindings` and `agent_oauth_bindings` rows for that agent are removed in the same transaction（FK 强制下不报约束错误，且不留孤儿绑定行）

#### Scenario: Delete of unknown agent returns False

- **WHEN** `agent_store.delete_agent("nope")` is called and no such agent exists
- **THEN** no rows are modified AND the call returns `False`

### Requirement: Agent name 为不可变标识
`agents.name` SHALL 是创建后不可变的标识符。系统 MUST NOT 提供改名能力（store / admin API / console 均无 rename 路径）——`agent_admin_state`（部署态键）、`session_meta.agent_name`（playground 归属）与 **per-agent 物理数据目录 `agents/<name>/data/`**（agent_state.db / 会话 / 向量的家）均以名字为键，改名会使部署态与历史会话失联、并令 agent 解析到空数据目录（全部运行数据被孤儿）。改名诉求 SHALL 以"创建新 agent + 按需显式迁移数据"满足。

#### Scenario: 无 rename 写路径
- **WHEN** 检查 `agent_store`、`agent_admin_store` 与 agent console API
- **THEN** 不存在修改 `agents.name` 的函数或端点

#### Scenario: 名字键 satellite 的一致性由不可变性保证
- **WHEN** agent 创建后正常运行任意时长
- **THEN** `agent_admin_state`、`session_meta` 与物理目录所用的名字键始终与 `agents.name` 一致（因其不可变）

### Requirement: Runtime agent resolution is file-sourced

At runtime the system SHALL resolve an agent's executable `AgentSnapshot` from its
self-contained file `agents/<name>/agent.yaml`, not from the
`agents`/`agent_versions` SQLite read path. The snapshot's runtime fields
(`system_prompt`, `allowed_tools`, `skills_dir`, `model_overrides`, `memory_namespace`)
SHALL come from the file, and the agent's runtime identity SHALL be its `name`. The DB
authoring requirements (creating `agents`/`agent_versions` rows via the admin console
and CLI) are unchanged; the file is the runtime artifact generated from them.

#### Scenario: Active snapshot resolved from file, not DB

- **WHEN** a message is routed to agent `assistant` and `agents/assistant/agent.yaml` exists
- **THEN** the applied `AgentSnapshot` (system_prompt, allowed_tools, skills_dir,
  model_overrides, memory_namespace) is read from that file and identified by the name
  `assistant`, with no `agents`/`agent_versions` read

#### Scenario: Missing agent file resolves to nothing

- **WHEN** routing references agent name `ghost` but no `agents/ghost/agent.yaml` exists
- **THEN** runtime resolution returns no snapshot and the request proceeds as a bare run

### Requirement: Agent 绑定表声明 agents.id 外键与级联
平台侧引用 agent 的从属/绑定表 SHALL 以 `agent_id`（INTEGER，= `agents.id`）声明 FK→`agents.id` ON DELETE CASCADE，使 agent 删除时其全部绑定/从属行由约束级联清理（不依赖应用层手工清理）。覆盖：`user_agents`、`channel_agents`、`agent_versions`、`mcp_servers`（正名后的 MCP 注册表）、`agent_secrets`（以及阶段 2/3 已处理的 `agent_kbs`、`agent_skills`、`agent_admin_state`、`session_meta`，与已带 FK 的 `agent_mcp_servers` 绑定表、`agent_oauth_bindings`）。例外：`connectors.agent_id` 为休眠列（运行路径未写入），不在本约束内，待真实接入再规整。

#### Scenario: 五表均带 agents.id FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `user_agents` / `channel_agents` / `agent_versions` / `mcp_servers` / `agent_secrets` 各声明 FK→`agents.id` ON DELETE CASCADE

#### Scenario: 删除 agent 级联清理全部绑定
- **WHEN** 一个持有用户分配 / 渠道绑定 / 版本 / MCP server 定义 / MCP 绑定 / secret 的 agent 被删除
- **THEN** 这些表中该 agent 的行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 休眠列不强加 FK
- **WHEN** 审视 `connectors.agent_id`
- **THEN** 它不声明 agents.id FK（休眠列、运行路径未消费），不在本约束范围

### Requirement: MCP server 注册表与绑定表命名对齐既有惯例
MCP 的两张管理表 SHALL 按"注册表 vs 绑定表"正名，与 skills/kbs 绑定家族及 `connectors` 注册表的既有命名惯例一致：MCP server 连接定义（含全局 `agent_id=NULL` 行）的注册表命名为 `mcp_servers`（无 `agent_` 前缀，对齐 `connectors`）；agent↔MCP server 的绑定表命名为 `agent_mcp_servers`（对齐 `agent_skills`/`agent_kbs`）。改名 SHALL 不改变运行时行为：materialize 的 MCP 解析（绑定取 id、注册表取定义）在新表名下结果不变。

#### Scenario: 注册表与绑定表名各就各位
- **WHEN** 管理库迁移运行到最新版本
- **THEN** 存在 `mcp_servers`（MCP server 定义注册表，原 `agent_mcp_servers`）与 `agent_mcp_servers`（agent↔server 绑定表，原 `agent_mcp_server_bindings`）；旧名 `agent_mcp_server_bindings` 不再存在

#### Scenario: 改名后 MCP 解析行为不变
- **WHEN** materialize 为某 agent 解析 MCP servers
- **THEN** 仍从绑定表（`agent_mcp_servers`）+ 版本快照 union 取 server_id，从注册表（`mcp_servers`）取定义（per-agent 行优先、全局 `agent_id=NULL` 行兜底），结果与改名前一致

