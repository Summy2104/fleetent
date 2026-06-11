## MODIFIED Requirements

### Requirement: Vector index synchronization
系统 SHALL 在创建 / 更新 / 删除 memory item 后,经**注入的 per-agent 向量后端**(`agent_vectors.db`，来自 `agent_scope(tenant, agent_id).vector_backend`)同步向量索引,MUST NOT 用全局 `vector_store` backend 自连。`mem:{user_id}` namespace 保留为该 per-agent 向量库内的按用户分区;embedding 仍用全局 provider(`vector_store.embed_text`)。

#### Scenario: Memory create upserts vector into injected backend
- **WHEN** memory item 被写入 SQLite
- **THEN** 系统经注入的 per-agent 向量后端 upsert 该向量,namespace 为 `mem:{user_id}`,不调用全局 `vector_store` backend 的 upsert

#### Scenario: 向量落本 agent 的 agent_vectors.db
- **WHEN** agent A 与 agent B 各自写入记忆
- **THEN** A 的向量落 A 的 `agent_vectors.db`、B 落 B 的,物理隔离,不共用一个全局向量库

### Requirement: Semantic memory search
`search()` SHALL 经**注入的 per-agent 向量后端**检索 memory ids(先用 `vector_store.embed_text` 嵌入 query,再经注入后端按 `mem:{user_id}` namespace 检索),回查 SQLite,并返回未过期 MemoryItem;MUST NOT 用全局 `vector_store` backend 检索。

#### Scenario: Search uses injected per-agent backend
- **WHEN** 调用 `search("user-1", "python debugging")`
- **THEN** 系统经注入的 per-agent 向量后端、按 namespace `mem:user-1` 检索,不调用全局 `vector_store` backend 的 search

#### Scenario: Search returns memory items in vector order
- **WHEN** 向量后端返回 memory ids `[id-2, id-1]`
- **THEN** `search()` 返回对应 MemoryItem，顺序保持 `[id-2, id-1]`

#### Scenario: Search filters expired context
- **WHEN** 向量后端返回一条 expires_at 早于当前时间的 context memory
- **THEN** `search()` 不返回该 memory

#### Scenario: Search skips missing ids
- **WHEN** 向量后端返回的 id 在 `memory_items` 中不存在
- **THEN** `search()` 跳过该 id
