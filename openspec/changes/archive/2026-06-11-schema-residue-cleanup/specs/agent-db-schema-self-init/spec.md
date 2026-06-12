# agent-db-schema-self-init Delta

## MODIFIED Requirements

### Requirement: memory_maintenance_proposals / skill_proposals 纳入统一 MIGRATIONS
memory 与 skill 的提案持久化 SHALL 统一在 per-agent `agent_state.db` 的 `reflection_proposals` 表（统一 `MIGRATIONS`：`runtime/agent_state_migrations.py`，单文件单 `user_version`；历史 `memory_maintenance_proposals` / `skill_proposals` 表已由后续版本 DROP），MUST NOT 由独立的 `ensure_schema` 旁路建表。`reflection._database()` 在未注入 `_state_db` 时 MUST NOT fallback 到 `Settings().database_url`（管理库）——无 per-agent state 注入即不得落管理库。管理库 MUST NOT 含 `memory_maintenance_proposals` / `skill_proposals` 副本表。

#### Scenario: 提案表经统一 MIGRATIONS 建立
- **WHEN** 某 agent 的 `agent_state.db` 以统一 `MIGRATIONS` 打开到最新版本
- **THEN** 提案持久化于 `reflection_proposals`（domain=`memory|skill`），且 `memory_maintenance_proposals` / `skill_proposals` 表不存在

#### Scenario: reflection 无 state 注入不落管理库
- **WHEN** `reflection` 在未注入 per-agent `_state_db` 的情况下访问提案存储
- **THEN** 不 fallback 到管理库（`Settings().database_url`）建/写任何提案表

#### Scenario: 管理库无提案副本表
- **WHEN** 管理库 Alembic 迁移运行到最新版本
- **THEN** 管理库不包含 `memory_maintenance_proposals` 与 `skill_proposals` 表
