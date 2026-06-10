## ADDED Requirements

### Requirement: traces / reflection 经 per-agent 嵌入式 Y 建 schema

`observability/traces.py`（`traces` 表）与 `reflection/reflection.py`（`reflection_reports` 表）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析、见 `tenant-scoped-db-routing`）的嵌入式 forward-only 迁移（Y）建立；二者 SHALL NOT 再以 `ensure_schema`-into-global 自建于全局 DB。DDL 原样 lift 进 per-agent 库 `MIGRATIONS`、行为不变。

#### Scenario: traces / reflection schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的 traces / reflection 存储
- **THEN** 其表经 `agent_scope` 取 `agent_state.db` 后由嵌入式迁移（Y）建立，而非 `ensure_schema`-into-global

#### Scenario: traces / reflection 行为不变

- **WHEN** 迁移后写入/读取 trace 或 reflection_report
- **THEN** 语义与迁移前一致（仅连接来源与 schema 机制改变）
