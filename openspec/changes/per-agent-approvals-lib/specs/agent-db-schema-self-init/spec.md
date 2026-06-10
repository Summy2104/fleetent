## ADDED Requirements

### Requirement: approvals 经 per-agent Y 建 schema、agent 侧唯一真相源

`governance/approval_store.py`（`approvals` 表）与 `approval_allowlist_store.py` 的 schema SHALL 经 per-agent `agent_state.db`（`agent_scope` 解析）的嵌入式 Y 建立；MUST NOT 再 `ensure_schema`-into-global。agent 侧 `approval_store` SHALL 为 approvals 的**唯一真相源**（R1：agent 全权写、platform 只读投影）；管理库 alembic SHALL NOT 再定义 `approvals` 表（孤立定义经迁移 drop）。

#### Scenario: approvals schema 经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的审批存储
- **THEN** `approvals` 经 `agent_scope` 取 `agent_state.db` 后由嵌入式 Y 建立

#### Scenario: 管理库不再定义 approvals

- **WHEN** `alembic upgrade head` 跑到最新
- **THEN** 管理库不含 `approvals` 表（孤立定义已 drop），approvals 仅存在于 per-agent 库

## REMOVED Requirements

### Requirement: Each agent-side store exposes ensure_schema
**Reason**: 至 3b-4，所有 agent 侧 store（KB / session / traces / reflection / memory / approvals）已迁入嵌入式 Y + `agent_scope`，无 store 再以 `ensure_schema`-into-global 自建，该过渡要求退役。
**Migration**: agent 侧 schema 一律经 per-agent `agent_state.db`（或 KB/共享库）的嵌入式 forward-only 迁移（Y）建立，经 `agent_scope`/`tenant_scope` 取连接（见 `tenant-scoped-db-routing` 与各库的 per-agent-Y 要求）。
