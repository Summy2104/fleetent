## ADDED Requirements

### Requirement: Memory domain terminology
Memory SHALL be treated as a capability domain, while the current memory-layer implementation SHALL be identified as User Memory.

#### Scenario: Current memory-layer is User Memory
- **WHEN** 文档或 spec 描述当前 `memory_layer`
- **THEN** 它被描述为 per-user semantic memory / User Memory
- **AND** 不暗示 Memory 能力域只能包含单用户记忆

#### Scenario: Shared Memory is a future sibling capability
- **WHEN** 文档描述 team、tenant、project 或 agent scoped memory
- **THEN** 它被描述为未来 Shared Memory sibling capability
- **AND** 不要求当前 `memory_items` 表支持 shared scope

### Requirement: User Memory remains user scoped
User Memory SHALL remain scoped by `user_id` in this change.

#### Scenario: User Memory table is not generalized
- **WHEN** memory-reflection-maintenance 完成
- **THEN** `memory_items` 仍以 `user_id` 表示 User Memory owner
- **AND** 系统不新增 `scope_type` 或 `scope_id` 来模拟 Shared Memory

#### Scenario: User Memory namespace remains user scoped
- **WHEN** User Memory 写入 vector_store
- **THEN** namespace 仍为 `mem:{user_id}`

### Requirement: User Memory controlled mutation boundary
memory-layer SHALL expose public mutation behavior that allows reflection to apply approved User Memory maintenance without direct SQL access.

#### Scenario: Reflection can apply approved changes through public API
- **WHEN** reflection 应用 approved User Memory maintenance proposal
- **THEN** 它可以通过 memory-layer public API 执行对应 mutation
- **AND** memory-layer 继续校验 target memory 属于当前 user_id

#### Scenario: Cross-user mutation is rejected
- **WHEN** mutation target 不属于当前 user_id
- **THEN** memory-layer 拒绝该 mutation
- **AND** 不修改任何 User Memory
