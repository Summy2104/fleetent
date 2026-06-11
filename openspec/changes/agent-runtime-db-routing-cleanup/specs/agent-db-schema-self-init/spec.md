## ADDED Requirements

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
