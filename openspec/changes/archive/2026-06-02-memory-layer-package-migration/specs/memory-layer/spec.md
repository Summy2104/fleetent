## ADDED Requirements

### Requirement: Memory package preserves user memory behavior
User Memory package migration SHALL preserve existing memory behavior while changing only code organization.

#### Scenario: Memory extraction behavior is preserved
- **WHEN** `extract_and_update()` processes a conversation
- **THEN** create、update、delete 和 ignore action 的处理语义保持不变
- **AND** extraction prompt 语义保持不变

#### Scenario: Memory search behavior is preserved
- **WHEN** `search()` returns semantically relevant User Memory items
- **THEN** vector search namespace 保持不变
- **AND** 返回顺序继续遵循 vector results
- **AND** 过期 memory 继续被过滤

#### Scenario: Memory operations behavior is preserved
- **WHEN** 调用 update、stale、delete 或 merge User Memory public operation
- **THEN** memory item 和 vector index 的更新语义保持不变

#### Scenario: Memory maintenance behavior is preserved
- **WHEN** 调用 `run_memory_maintenance()`
- **THEN** expired context、over-limit 和 duplicate compaction 的 dry-run / apply 语义保持不变
- **AND** retention / compaction 策略保持不变

#### Scenario: Memory schema is unchanged
- **WHEN** 本 change 完成
- **THEN** `memory_items` schema 不变
- **AND** 不新增 Alembic migration
