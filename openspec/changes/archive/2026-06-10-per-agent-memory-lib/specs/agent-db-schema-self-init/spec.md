## ADDED Requirements

### Requirement: memory 经 per-agent 嵌入式 Y 建 schema

`memory/store.py`（`memory_items` 表）的 schema SHALL 经 per-agent `agent_state.db`（由 `agent_scope(tenant, agent_id)` 解析）的嵌入式 forward-only 迁移（Y）建立；MUST NOT 再以 `ensure_schema`-into-global 自建。`memory_items` SHALL NOT 含 `namespace` 列（agent 隔离由 per-agent 物理库提供，见 memory-layer）。

#### Scenario: memory schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的 memory 存储
- **THEN** `memory_items` 经 `agent_scope` 取 `agent_state.db` 后由嵌入式迁移（Y）建立，且不含 `namespace` 列
