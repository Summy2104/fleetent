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
- **WHEN** 调用方从 memory_layer 导入 `MemoryItem`、`extract_and_update` 和 `search`
- **THEN** 导入成功

#### Scenario: Legacy load_memories is removed
- **WHEN** 调用方从 memory_layer 导入 `load_memories`
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
agent-runtime SHALL 不再直接调用 memory_layer 加载最近 memory 并注入 system prompt。

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
