## ADDED Requirements

### Requirement: Shared Memory model
系统 SHALL 提供独立于 User Memory 的 Shared Memory 实体，用于保存经过确认的共享上下文、偏好和操作惯例。

#### Scenario: Shared memory schema exists
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 memory-owned `shared_memory_items` 表
- **AND** 表包含 id、scope_type、scope_id、type、content、status、source、source_ref、created_by、created_at 和 updated_at

#### Scenario: Supported shared memory scopes
- **WHEN** Shared Memory 被创建
- **THEN** `scope_type` 只能是 `team` 或 `tenant`

#### Scenario: Supported shared memory types
- **WHEN** Shared Memory 被创建
- **THEN** `type` 只能是 `context`、`preference` 或 `procedure`

#### Scenario: Supported shared memory statuses
- **WHEN** Shared Memory 状态被设置
- **THEN** `status` 只能是 `active`、`stale` 或 `archived`

### Requirement: Shared Memory public API
系统 SHALL 提供 Shared Memory 的创建、更新、归档、检索和 reindex public API。

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `SharedMemoryItem`、`create_shared_memory`、`update_shared_memory`、`archive_shared_memory`、`search_shared_memory` 和 `iter_indexable_shared_memories`
- **THEN** 导入成功

#### Scenario: Empty content is rejected
- **WHEN** 创建或更新 Shared Memory 时 content 为空或全空白
- **THEN** 系统 fail fast

### Requirement: Shared Memory vector synchronization
系统 SHALL 将 active / stale Shared Memory 同步到 vector_store，并按 scope 隔离。

#### Scenario: Create upserts vector
- **WHEN** Shared Memory item 被创建
- **THEN** 系统调用 `vector_store.upsert(item_id, content, "shared:{scope_type}:{scope_id}")`

#### Scenario: Update upserts vector
- **WHEN** active 或 stale Shared Memory content 被更新
- **THEN** 系统调用 `vector_store.upsert(item_id, content, "shared:{scope_type}:{scope_id}")`

#### Scenario: Archive deletes vector
- **WHEN** Shared Memory item 被归档
- **THEN** 系统调用 `vector_store.delete(item_id, "shared:{scope_type}:{scope_id}")`

### Requirement: Shared Memory search
`search_shared_memory()` SHALL 通过 vector_store 检索指定 scope 内的 active / stale Shared Memory。

#### Scenario: Search is scope isolated
- **WHEN** team A 和 team B 存在相似 Shared Memory
- **THEN** 查询 team A 不返回 team B 的 item

#### Scenario: Search excludes archived items
- **WHEN** vector_store 返回 archived item id
- **THEN** `search_shared_memory()` 跳过该 item

#### Scenario: Search preserves vector order
- **WHEN** vector_store 返回 ids `[id-2, id-1]`
- **THEN** `search_shared_memory()` 按 `[id-2, id-1]` 返回匹配 items

### Requirement: Shared Memory reindex boundary
Shared Memory SHALL 提供 public iterator，供 vector_store reindex 使用，而不是让 reindex 直接查询内部表。

#### Scenario: Indexable shared memories are scoped
- **WHEN** 调用 `iter_indexable_shared_memories(scope_type, scope_id)`
- **THEN** 返回结果只包含该 scope 的 active / stale items
- **AND** 每个 item 包含 id、content 和 namespace `shared:{scope_type}:{scope_id}`

### Requirement: Shared Memory proposal apply
系统 SHALL 支持将 approved reflection proposal 受控应用为 Shared Memory。

#### Scenario: Approved proposal creates shared memory
- **WHEN** approved proposal target 为 `shared_memory`
- **AND** proposal 包含合法 scope、type 和 content
- **THEN** apply 入口创建或更新 Shared Memory
- **AND** source 记录为 `reflection_proposal`

#### Scenario: Unapproved proposal is rejected
- **WHEN** proposal 状态不是 approved
- **THEN** apply 入口 fail fast
- **AND** 不创建或更新 Shared Memory

### Requirement: Shared Memory does not inject prompt directly
shared-memory change SHALL NOT 自动接入 long-term context prompt 注入。

#### Scenario: No automatic context provider
- **WHEN** Shared Memory item 被创建
- **THEN** agent run 不会因此自动注入该 item

#### Scenario: Injection policy is deferred
- **WHEN** 需要决定 User Memory、Shared Memory 和 Knowledge Base 的 budget 或优先级
- **THEN** 该行为由后续 `long-term-context-agent-tenant-policy` 定义
