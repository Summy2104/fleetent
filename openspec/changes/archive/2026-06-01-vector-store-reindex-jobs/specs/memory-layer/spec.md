## ADDED Requirements

### Requirement: Memory indexable iterator
memory-layer SHALL 提供 public API，用于枚举指定用户当前应写入 vector_store 的 memory source records。

#### Scenario: Memory indexable API is importable
- **WHEN** 调用方从 `fleetent.memory_layer` 导入 `iter_indexable_memories`
- **THEN** 导入成功

#### Scenario: Memory indexable items are user scoped
- **WHEN** 用户 A 和用户 B 都有 memory items
- **AND** 调用 `iter_indexable_memories(user_a)`
- **THEN** 返回结果只包含用户 A 的 memory items

#### Scenario: Memory indexable items exclude expired context
- **WHEN** 用户存在已过期 context memory
- **THEN** `iter_indexable_memories()` 不返回该 expired memory

#### Scenario: Memory indexable item namespace
- **WHEN** `iter_indexable_memories()` 返回 item
- **THEN** item.namespace 等于 `memory_namespace(user_id)`
- **AND** item.id 等于 memory item id
- **AND** item.content 等于 memory item content

### Requirement: Memory indexable iterator is a public boundary
vector_store reindex SHALL consume memory indexable records through memory-layer public API, not direct SQL.

#### Scenario: Reindex does not query memory table directly
- **WHEN** memory reindex 执行
- **THEN** reindex code 调用 `memory_layer.iter_indexable_memories()`
- **AND** 不直接访问 `memory_items` 表
