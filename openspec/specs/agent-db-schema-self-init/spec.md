# agent-db-schema-self-init Specification

## Purpose
standalone agent 进程（`fleetent agent run <id>`）启动时自动建立 agent-side DB schema，
无需外部 alembic 步骤。agent 运行时表由 per-agent / per-tenant 物理库上的统一嵌入式
`MIGRATIONS` 建立；管理库 schema 仅由 alembic 维护。

## Requirements

### Requirement: _start_infra initializes agent DB schema before any store access

`agent_app._start_infra()` SHALL call `_init_agent_db_schema()` as its first operation,
before session maintenance or any other infra initialization. `_init_agent_db_schema()`
SHALL create all agent-side tables in the DB pointed to by `DATABASE_URL`.

#### Scenario: Fresh agent DB gets all tables on first boot

- **WHEN** `fleetent agent run my-bot` starts with a fresh `agents/my-bot/data/fleetent.db`
- **THEN** after `_start_infra()` completes, the following tables SHALL exist:
  `traces`, `memory_items`, `reflection_reports`, `knowledge_bases`, `knowledge_documents`,
  `knowledge_chunks`, `chunks_fts`, `knowledge_source_states`

#### Scenario: Existing agent DB is unaffected (idempotent)

- **WHEN** `_init_agent_db_schema()` is called on a DB that already has all tables
- **THEN** no error is raised and no data is modified

### Requirement: 管理库不再定义 traces / memory_items / reflection_reports

管理库 alembic SHALL NOT 再定义 `traces` / `memory_items` / `reflection_reports` 表。
它们是 agent 侧运行时表，唯一真相源为 per-agent `agent_state.db` 的统一 `MIGRATIONS`
（Y）。这三张表在 alembic 中的历史定义 SHALL 经 forward-drop 迁移移除，使管理库
不再建出永不被写的孤儿 agent 表。

#### Scenario: 管理库 alembic head 不含这三表

- **WHEN** 全新管理库执行 `alembic upgrade head`
- **THEN** 库中不含 `traces` / `memory_items` / `reflection_reports` 表

#### Scenario: agent 侧仍由 Y 建这三表

- **WHEN** 某 agent 的 `agent_state.db` 以统一 `MIGRATIONS` 打开
- **THEN** `traces` / `memory_items` / `reflection_reports` 由 Y 建立，读写经 `agent_scope` 落该 agent 的库，与管理库无关

### Requirement: session 元数据纳入 agent DB 自建

`_init_agent_db_schema()` SHALL 调用 `session.index.ensure_schema`，使 session 元数据表随其它
agent-side 表在 boot 时一并建立于 per-agent 库。

#### Scenario: session 元数据表随 boot 建立

- **WHEN** `fleetent agent run` 完成 `_start_infra()`
- **THEN** per-agent 库中存在 session 元数据表（`sessions`），且与其它 agent-side 表同库

### Requirement: memory 经 per-agent 嵌入式 Y 建 schema

`memory/store.py`（`memory_items` 表）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析）的嵌入式 forward-only 迁移（Y）建立；MUST NOT 再以 `ensure_schema`-into-global 自建。`memory_items` SHALL NOT 含 `namespace` 列（agent 隔离由 per-agent 物理库提供，见 memory-layer）。

#### Scenario: memory schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的 memory 存储
- **THEN** `memory_items` 经 `agent_scope` 取 `agent_state.db` 后由嵌入式迁移（Y）建立，且不含 `namespace` 列

### Requirement: traces / reflection 经 per-agent 嵌入式 Y 建 schema

`observability/traces.py`（`traces` 表）与 `reflection/reflection.py`（`reflection_reports` 表）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析、见 `tenant-scoped-db-routing`）的嵌入式 forward-only 迁移（Y）建立；二者 SHALL NOT 再以 `ensure_schema`-into-global 自建于全局 DB。DDL 原样 lift 进 per-agent 库 `MIGRATIONS`、行为不变。

#### Scenario: traces / reflection schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的 traces / reflection 存储
- **THEN** 其表经 `agent_scope` 取 `agent_state.db` 后由嵌入式迁移（Y）建立，而非 `ensure_schema`-into-global

#### Scenario: traces / reflection 行为不变

- **WHEN** 迁移后写入/读取 trace 或 reflection_report
- **THEN** 语义与迁移前一致（仅连接来源与 schema 机制改变）

### Requirement: approvals 经 per-agent Y 建 schema、agent 侧唯一真相源

`governance/approval_store.py`（`approvals` 表）与 `approval_allowlist_store.py` 的 schema SHALL 经 per-agent `agent_state.db`（`agent_scope` 解析）的嵌入式 Y 建立；MUST NOT 再 `ensure_schema`-into-global。agent 侧 `approval_store` SHALL 为 approvals 的**唯一真相源**（R1：agent 全权写、platform 只读投影）；管理库 alembic SHALL NOT 再定义 `approvals` 表（孤立定义经迁移 drop）。

#### Scenario: approvals schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的审批存储
- **THEN** `approvals` 经 `agent_scope` 取 `agent_state.db` 后由嵌入式 Y 建立

#### Scenario: 管理库不再定义 approvals

- **WHEN** `alembic upgrade head` 跑到最新
- **THEN** 管理库不含 `approvals` 表（孤立定义已 drop），approvals 仅存在于 per-agent 库

### Requirement: session_anti_flap / sub_agent_runs 经 per-agent Y 建 schema
`runtime/context.py`（`session_anti_flap` 表，压缩防抖）与 `runtime/sub_agent_lifecycle.py`（`sub_agent_runs` 表，子 agent 生命周期）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析、见 `tenant-scoped-db-routing`）的嵌入式 forward-only 迁移（Y）建立，读写 SHALL 经统一 `db.py` 边界。二者 MUST NOT 再 `from fleetent.user_store import DB_PATH` 后裸 `sqlite3.connect(DB_PATH)`——该路径在 platform 多 agent 下会把 agent 运行时数据写入共享管理库，违反「agent 数据只落 agent 侧」与物理隔离。DDL 原样 lift 进统一 `MIGRATIONS`、行为不变。

#### Scenario: session_anti_flap / sub_agent_runs 落各自 agent_state.db
- **WHEN** platform 下两个不同 agent 分别写压缩防抖 / 子 agent 运行记录
- **THEN** 各自写入自己的 per-agent `agent_state.db`（经 `agent_scope` 解析），互不可见，且都不写入共享管理库

#### Scenario: 不再裸连全局 DB_PATH
- **WHEN** 审视 `runtime/context.py` 与 `runtime/sub_agent_lifecycle.py`
- **THEN** 不存在 `sqlite3.connect(DB_PATH)` 形式的全局连接；连接经统一 `db.py` / 路由获取

### Requirement: memory_maintenance_proposals / skill_proposals 纳入统一 MIGRATIONS
`memory/proposal_store.py`（`memory_maintenance_proposals`）与 `reflection/reflection.py`（`skill_proposals`）所用表的 schema SHALL 由 per-agent `agent_state.db` 的**统一 `MIGRATIONS`**（`runtime/agent_state_migrations.py`，单文件单 `user_version`）建立，MUST NOT 由各自独立的 `ensure_schema` 旁路建表。`reflection._database()` 在未注入 `_state_db` 时 MUST NOT fallback 到 `Settings().database_url`（管理库）——无 per-agent state 注入即不得落管理库。

#### Scenario: 两表经统一 MIGRATIONS 建立
- **WHEN** 某 agent 的 `agent_state.db` 以统一 `MIGRATIONS` 打开
- **THEN** `memory_maintenance_proposals` 与 `skill_proposals` 由该统一迁移列表建立（append 在当前最大版本之后），不依赖独立 `ensure_schema`

#### Scenario: reflection 无 state 注入不落管理库
- **WHEN** `reflection` 在未注入 per-agent `_state_db` 的情况下访问 `skill_proposals`
- **THEN** 不 fallback 到管理库（`Settings().database_url`）建/写该表

### Requirement: budget_usage 经 per-agent Y 建 schema

`runtime/layered_budget.py`（`budget_usage` 表，分层 turns/tokens 跨 run 计数）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析）的统一 `MIGRATIONS`（`runtime/agent_state_migrations.py`，单文件单 `user_version`）建立，读写 SHALL 经统一 `db.py` 边界。`layered_budget` MUST NOT 再 `from fleetent.user_store import DB_PATH` 后裸 `sqlite3.connect`——该路径在 platform 多 agent 下会把 agent 预算计数写入共享管理库。DDL 原样 lift 进统一 `MIGRATIONS`（append 在当前最大版本之后）、行为不变。`budget_usage` 仅持久化跨 run scope（cross-agent/global scope 已删，task scope 不持久化）。

#### Scenario: budget_usage 落各自 agent_state.db
- **WHEN** platform 下两个不同 agent 各自累计预算用量
- **THEN** 各写入自己的 per-agent `agent_state.db`（经 `agent_scope`），互不可见，且都不写入共享管理库

#### Scenario: budget_usage 经统一 MIGRATIONS 建立
- **WHEN** 某 agent 的 `agent_state.db` 以统一 `MIGRATIONS` 打开
- **THEN** `budget_usage` 由该统一迁移列表建立（append 在当前最大版本之后），不依赖独立 `init_db` 旁路

#### Scenario: 不再裸连全局 DB_PATH
- **WHEN** 审视 `runtime/layered_budget.py`
- **THEN** 不存在 `from user_store import DB_PATH` + `sqlite3.connect(DB_PATH)` 形式的连接；连接经 `agent_scope` + `db.py` 获取
