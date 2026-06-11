# memory-layer Delta

## MODIFIED Requirements

### Requirement: Shared Memory model
系统 SHALL 提供独立于 User Memory 的 Shared Memory 实体，用于保存经过确认的共享上下文、偏好和操作惯例。`shared_memory_items` 表 SHALL 仅由 per-tenant `shared_memory.db` 的嵌入式 forward-only 迁移持有；管理库 MUST NOT 含同名副本表（单一真相源）。

#### Scenario: Shared memory schema exists
- **WHEN** per-tenant `shared_memory.db` 的嵌入式迁移运行到最新版本
- **THEN** 该库包含 memory-owned `shared_memory_items` 表
- **AND** 表包含 id、scope_type、scope_id、type、content、status、source、source_ref、created_by、created_at 和 updated_at

#### Scenario: 管理库无副本表
- **WHEN** 管理库 Alembic 迁移运行到最新版本
- **THEN** 管理库不包含 `shared_memory_items` 表

#### Scenario: Supported shared memory scopes
- **WHEN** Shared Memory 被创建
- **THEN** `scope_type` 只能是 `team` 或 `tenant`

#### Scenario: Supported shared memory types
- **WHEN** Shared Memory 被创建
- **THEN** `type` 只能是 `context`、`preference` 或 `procedure`

#### Scenario: Supported shared memory statuses
- **WHEN** Shared Memory 状态被设置
- **THEN** `status` 只能是 `active`、`stale` 或 `archived`
