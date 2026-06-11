## ADDED Requirements

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
