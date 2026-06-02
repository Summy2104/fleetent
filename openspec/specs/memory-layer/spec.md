# memory-layer Specification

## Purpose
Define structured per-user semantic memory storage, extraction, vector indexing, and retrieval behavior.
## Requirements
### Requirement: Structured semantic memory model
系统 SHALL 将 per-user semantic memory 存储为 SQLite `memory_items` 表中的结构化记录。

#### Scenario: Migration creates memory_items
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 `memory_items` 表

#### Scenario: Memory item fields
- **WHEN** memory item 被写入
- **THEN** 记录包含 id、user_id、type、content、created_at、updated_at 和 expires_at

### Requirement: Memory public API
系统 SHALL 提供 `MemoryItem`、`extract_and_update(user_id, conversation)` 和
`search(user_id, query, limit)` public API。

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `MemoryItem`、`extract_and_update` 和 `search`
- **THEN** 导入成功

#### Scenario: Legacy load_memories is removed
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `load_memories`
- **THEN** 导入失败或该名称不存在

### Requirement: No JSONL memory compatibility
系统 SHALL 删除旧 JSONL memory 写入语义，不导入旧 JSONL 文件。

#### Scenario: Extract does not write JSONL
- **WHEN** `extract_and_update()` 成功写入 memory
- **THEN** 系统不会创建或追加 `data/users/{user_id}/memories.jsonl`

### Requirement: Memory extraction actions
`extract_and_update()` SHALL 调用 memory_extraction 模型，并处理 `create`、`update`、`delete`
与 `ignore` action。

#### Scenario: Create action writes memory
- **WHEN** LLM 返回 action=`create`、合法 type 和非空 content
- **THEN** 系统写入一条 memory item
- **AND** 调用 `vector_store.upsert()` 同步索引

#### Scenario: Update action changes existing memory
- **WHEN** LLM 返回 action=`update`、合法 `target_id`、合法 type 和非空 content
- **THEN** 系统更新该 memory item 的 content 和 updated_at
- **AND** 调用 `vector_store.upsert(target_id, content, memory_namespace(user_id))`

#### Scenario: Context update refreshes TTL
- **WHEN** context memory 被 update
- **THEN** expires_at 被刷新为 updated_at 后 30 天

#### Scenario: Identity and preferences update do not expire
- **WHEN** identity 或 preferences memory 被 update
- **THEN** expires_at 为 NULL

#### Scenario: Delete action removes existing memory
- **WHEN** LLM 返回 action=`delete` 和合法 `target_id`
- **THEN** 系统删除该 memory item
- **AND** 调用 `vector_store.delete(target_id, memory_namespace(user_id))`

#### Scenario: Ignore action does not mutate memory
- **WHEN** LLM 返回 action=`ignore`
- **THEN** 系统不写入、不更新、不删除 memory item

#### Scenario: Invalid mutation output is ignored
- **WHEN** LLM 返回非法 JSON、未知 action、非法 type、空 content、缺失 target_id 或不属于当前用户的 target_id
- **THEN** 系统跳过对应输出，不向 agent_runtime 抛出异常

### Requirement: Memory type TTL rules
系统 SHALL 支持 `identity`、`preferences` 和 `context` 三种 memory type，并按类型设置过期时间。

#### Scenario: Context memory expires
- **WHEN** context memory 被创建
- **THEN** expires_at 默认为 created_at 后 30 天

#### Scenario: Identity and preferences do not expire by default
- **WHEN** identity 或 preferences memory 被创建
- **THEN** expires_at 为 NULL

### Requirement: Vector index synchronization
系统 SHALL 在创建 memory item 后同步写入 vector_store。

#### Scenario: Memory create upserts vector
- **WHEN** memory item 被写入 SQLite
- **THEN** 系统调用 `vector_store.upsert(memory_id, content, memory_namespace(user_id))`

### Requirement: Semantic memory search
`search()` SHALL 通过 vector_store 检索 memory ids，回查 SQLite，并返回未过期 MemoryItem。

#### Scenario: Search uses vector namespace
- **WHEN** 调用 `search("user-1", "python debugging")`
- **THEN** 系统查询 vector_store namespace `mem:user-1`

#### Scenario: Search returns memory items in vector order
- **WHEN** vector_store 返回 memory ids `[id-2, id-1]`
- **THEN** `search()` 返回对应 MemoryItem，顺序保持 `[id-2, id-1]`

#### Scenario: Search filters expired context
- **WHEN** vector_store 返回一条 expires_at 早于当前时间的 context memory
- **THEN** `search()` 不返回该 memory

#### Scenario: Search skips missing ids
- **WHEN** vector_store 返回的 id 在 `memory_items` 中不存在
- **THEN** `search()` 跳过该 id

### Requirement: Agent runtime no longer injects memory directly
agent-runtime SHALL 不再直接绕过 `fleetent.intelligence.memory` public API 加载最近 memory 并注入 system prompt。

#### Scenario: Agent run does not call load_memories
- **WHEN** agent_loop 执行 run 或 run_stream
- **THEN** 不调用 `load_memories()`，也不直接追加 `[Memory]` prompt 区段

### Requirement: Existing memory snapshot for extraction
`extract_and_update()` SHALL 在调用 memory_extraction 模型时提供有限的现有 memory snapshot，
供模型判断 create、update、delete 或 ignore。

#### Scenario: Snapshot includes bounded memory by type
- **WHEN** `extract_and_update()` 构造 extraction 输入
- **THEN** identity snapshot 最多包含 20 条
- **AND** preferences snapshot 最多包含 30 条
- **AND** context snapshot 最多包含 20 条

#### Scenario: Snapshot excludes expired context
- **WHEN** 用户存在已过期 context memory
- **THEN** extraction snapshot 不包含该 memory

#### Scenario: Snapshot belongs to current user only
- **WHEN** 系统为 user A 执行 extraction
- **THEN** snapshot 不包含其他用户的 memory item

### Requirement: Memory conflict handling through update actions
系统 SHALL 通过 extraction action contract 处理明显冲突和一次性偏好请求，避免无界追加矛盾记忆。

#### Scenario: Identity conflict updates existing item
- **WHEN** 用户新对话修正了已有 identity 事实，且 LLM 返回 update action
- **THEN** 系统更新目标 identity memory
- **AND** 不追加一条矛盾 identity memory

#### Scenario: Context conflict updates existing item
- **WHEN** 用户新对话修正了已有 context 状态，且 LLM 返回 update action
- **THEN** 系统更新目标 context memory
- **AND** 刷新 context TTL

#### Scenario: One-off preference is ignored
- **WHEN** 用户只提出一次性格式或输出要求，且 LLM 返回 ignore action
- **THEN** 系统不创建 preferences memory

### Requirement: Memory extraction evaluation fixtures
系统 SHALL 提供 memory extraction evaluation fixtures，用于通过 mock actions 驱动提取流程，并验证最终 memory 状态。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、initial_memories、conversation、mock_actions、expected_memories 和 forbidden_memories

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段或包含非法 action 类型
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic memory extraction evaluation
系统 SHALL 默认通过 mock LLM 运行 memory extraction evaluation，保证评估稳定且不依赖外部模型。

#### Scenario: Mock actions drive extraction
- **WHEN** evaluation fixture 提供 mock_actions
- **THEN** evaluation runner 使用 mock_actions 驱动 `extract_and_update()`
- **AND** 不调用真实 LLM 服务

#### Scenario: Expected memory state is validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_memories 对应的 memory 状态存在

#### Scenario: Forbidden memory state is rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_memories 对应的 memory 状态不存在

#### Scenario: Evaluation isolates storage and vector dependencies
- **WHEN** evaluation case 运行
- **THEN** SQLite 使用 tmp path 隔离
- **AND** vector_store 被 mock 或使用测试替身
- **AND** 不触碰 `data/`

### Requirement: Memory extraction scenario coverage
系统 SHALL 覆盖第一批 memory extraction 质量基线场景。

#### Scenario: Identity create is covered
- **WHEN** 用户首次提供稳定身份事实
- **THEN** evaluation 验证最终存在对应的 identity memory

#### Scenario: Identity update is covered
- **WHEN** 用户修正已有身份事实
- **THEN** evaluation 验证最终 identity memory 已更新为新事实

#### Scenario: Context update is covered
- **WHEN** 用户更新当前项目或临时状态
- **THEN** evaluation 验证最终 context memory 已更新为新状态

#### Scenario: Preference create is covered
- **WHEN** 用户明确表达长期偏好
- **THEN** evaluation 验证最终存在对应的 preferences memory

#### Scenario: One-off preference request is covered
- **WHEN** 用户只提出一次性格式或输出要求
- **THEN** evaluation 验证最终不存在对应的一次性 preferences memory

#### Scenario: Explicit forget is covered
- **WHEN** 用户明确要求忘记某条记忆
- **THEN** evaluation 验证最终不存在被遗忘的 memory

#### Scenario: Noisy conversation ignore is covered
- **WHEN** 对话没有可记忆事实或内容噪声较多
- **THEN** evaluation 验证最终不新增 memory

### Requirement: Optional real LLM memory extraction evaluation
系统 SHALL 提供显式启用的真实 LLM memory extraction evaluation 入口，且默认跳过。

#### Scenario: Real LLM evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** 真实 LLM evaluation case 被 skip

#### Scenario: Real LLM evaluation requires explicit opt-in
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** runner 可以使用真实 `memory_extraction` 路由运行 fixture

#### Scenario: Real LLM evaluation skips when provider credentials are missing
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1` 但缺少真实 provider API key
- **THEN** 真实 LLM evaluation case 被 skip

#### Scenario: Real LLM evaluation is not a PR gate
- **WHEN** Bitbucket PR/main pipeline 运行
- **THEN** pipeline 不默认运行真实 LLM evaluation

### Requirement: Memory indexable iterator
`fleetent.intelligence.memory` SHALL provide public API for enumerating the current
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
`fleetent.intelligence.memory` SHALL provide a per-user public API for dry-run and apply memory retention maintenance through
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

### Requirement: Memory retention dry-run
`fleetent.intelligence.memory` SHALL support dry-run retention maintenance that reports eligible rows without mutation.

#### Scenario: Dry-run reports expired context rows
- **WHEN** user has context memory with `expires_at` before now
- **AND** maintenance runs with dry_run enabled
- **THEN** summary reports the expired memory id
- **AND** SQLite row remains
- **AND** vector_store.delete is not called

#### Scenario: Dry-run reports over-limit rows
- **WHEN** user has more memories of a type than policy allows
- **AND** maintenance runs with dry_run enabled
- **THEN** summary reports older over-limit memory ids
- **AND** SQLite rows remain
- **AND** vector_store.delete is not called

### Requirement: Memory retention apply
`fleetent.intelligence.memory` SHALL delete eligible per-user memory rows and matching vectors when retention maintenance is applied.

#### Scenario: Apply deletes expired context rows
- **WHEN** user has context memory with `expires_at` before now
- **AND** maintenance runs with dry_run disabled
- **THEN** expired context row is deleted from `memory_items`
- **AND** vector_store.delete is called for that memory id

#### Scenario: Apply deletes older over-limit rows
- **WHEN** user has more memories of a type than policy allows
- **AND** maintenance runs with dry_run disabled
- **THEN** newest memories within the limit are retained
- **AND** older over-limit rows are deleted

### Requirement: Memory duplicate compaction
`fleetent.intelligence.memory` SHALL provide deterministic duplicate compaction candidates within the same user and memory type.

#### Scenario: Duplicate candidate is reported
- **WHEN** user has multiple memories of the same type with identical normalized content
- **THEN** maintenance summary includes a compaction candidate with one canonical id and duplicate ids

#### Scenario: Newest duplicate is canonical
- **WHEN** duplicate memories have different updated_at values
- **THEN** canonical id is the newest row, using id as stable tie-breaker

#### Scenario: Apply duplicate compaction removes duplicates
- **WHEN** maintenance runs with dry_run disabled and duplicate compaction enabled
- **THEN** duplicate ids are deleted
- **AND** canonical id remains

### Requirement: Memory domain terminology
Memory SHALL be treated as a capability domain, while the current `fleetent.intelligence.memory` implementation SHALL be identified as User Memory.

#### Scenario: Current memory implementation is User Memory
- **WHEN** 文档或 spec 描述当前 `fleetent.intelligence.memory`
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
`fleetent.intelligence.memory` SHALL expose public mutation behavior that allows reflection to apply approved User Memory maintenance without direct SQL access.

#### Scenario: Reflection can apply approved changes through public API
- **WHEN** reflection 应用 approved User Memory maintenance proposal
- **THEN** 它可以通过 `fleetent.intelligence.memory` public API 执行对应 mutation
- **AND** `fleetent.intelligence.memory` 继续校验 target memory 属于当前 user_id

#### Scenario: Cross-user mutation is rejected
- **WHEN** mutation target 不属于当前 user_id
- **THEN** `fleetent.intelligence.memory` 拒绝该 mutation
- **AND** 不修改任何 User Memory

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
