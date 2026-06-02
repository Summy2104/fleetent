## MODIFIED Requirements

### Requirement: Memory indexable iterator
memory-layer SHALL provide public API through `fleetent.intelligence.memory` for enumerating the current
memory source records that should be written to vector_store for a user.

#### Scenario: Memory indexable API is importable
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `iter_indexable_memories`
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
vector_store reindex SHALL consume memory indexable records through `fleetent.intelligence.memory` public
API, not direct SQL.

#### Scenario: Reindex does not query memory table directly
- **WHEN** memory reindex 执行
- **THEN** reindex code 调用 `fleetent.intelligence.memory.iter_indexable_memories()`
- **AND** 不直接访问 `memory_items` 表

### Requirement: Memory semantic retrieval embedding evaluation
系统 SHALL 提供 memory semantic retrieval embedding evaluation fixture，用于验证 memory search 经由
vector-store embedding / reindex 路径后的召回行为。

#### Scenario: Memory retrieval fixture is explicit
- **WHEN** evaluation runner 加载 combined embedding fixture
- **THEN** fixture 包含 memory records、memory queries、expected memory snippets 和 forbidden memory snippets

#### Scenario: Memory index is rebuilt through public reindex
- **WHEN** deterministic combined embedding evaluation 运行
- **THEN** runner 调用 `vector_store.reindex(ReindexRequest(owner="memory", user_id=...))`

#### Scenario: Expected memory snippets are retrieved
- **WHEN** memory query 运行完成
- **THEN** runner 验证 expected memory snippets 出现在 `fleetent.intelligence.memory.search()` top-k 结果中

#### Scenario: Forbidden memory snippets are rejected
- **WHEN** memory query 运行完成
- **THEN** runner 验证 forbidden memory snippets 不出现在 `fleetent.intelligence.memory.search()` top-k 结果中

### Requirement: Memory retention maintenance public API
memory-layer SHALL provide a per-user public API for dry-run and apply memory retention maintenance through
`fleetent.intelligence.memory`.

#### Scenario: Maintenance API is importable
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 maintenance policy、summary、candidate dataclasses 和 `run_memory_maintenance`
- **THEN** 导入成功

#### Scenario: Invalid maintenance request fails fast
- **WHEN** caller passes empty user_id or negative per-type limits
- **THEN** maintenance API raises a validation error

#### Scenario: Maintenance is user scoped
- **WHEN** caller runs maintenance for user A
- **THEN** maintenance does not delete user B memory rows
- **AND** vector deletion namespace is `mem:{user_a}`
