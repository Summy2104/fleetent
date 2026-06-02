## ADDED Requirements

### Requirement: Vector store public API
系统 SHALL 提供 `fleetent.intelligence.vector_store` public API，供 memory 和 knowledge-base 写入、
检索和删除向量索引。

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.intelligence.vector_store` 导入 `SearchResult`、`upsert`、`search` 和 `delete`
- **THEN** 导入成功

#### Scenario: Search result only exposes id and score
- **WHEN** 调用方收到 `SearchResult`
- **THEN** 结果只包含调用方写入的 `id` 和相似度 `score`

### Requirement: Vector store configuration
系统 SHALL 提供 vector store 和 embedding 配置默认值。当前版本 SHALL 默认使用 in-memory vector backend
和 deterministic embedding backend。

#### Scenario: Default vector store config
- **WHEN** 未显式配置 vector store
- **THEN** `vector_store.backend` 默认为 `memory`

#### Scenario: Default embedding config
- **WHEN** 未显式配置 embedding
- **THEN** `embedding.backend` 默认为 `deterministic`，`embedding.dimensions` 默认为 64

#### Scenario: Unsupported backend fails fast
- **WHEN** 配置了当前不支持的 vector backend 或 embedding backend
- **THEN** 初始化失败，并明确说明当前支持的 backend

### Requirement: Namespace helpers
系统 SHALL 提供固定 namespace helper，避免调用方手写 namespace 字符串。

#### Scenario: Memory namespace
- **WHEN** 调用 `memory_namespace("user-1")`
- **THEN** 返回 `mem:user-1`

#### Scenario: Knowledge namespace
- **WHEN** 调用 `knowledge_namespace("default", "global")`
- **THEN** 返回 `kb:default:global`

#### Scenario: Empty namespace part is invalid
- **WHEN** namespace helper 收到空 user_id、tenant_id 或 kb_id
- **THEN** 系统抛出 `ValueError`

### Requirement: Deterministic embedding backend
系统 SHALL 提供 deterministic embedding backend，用于测试和本地开发。

#### Scenario: Same text embeds identically
- **WHEN** 同一文本被 embedding 两次
- **THEN** 两次返回相同向量

#### Scenario: Embedding dimension is stable
- **WHEN** 使用默认配置生成 embedding
- **THEN** 返回向量维度为 64

#### Scenario: Non-empty embedding is normalized
- **WHEN** 非空文本被 embedding
- **THEN** 返回向量被归一化，便于相似度计算

### Requirement: In-memory vector backend
系统 SHALL 提供 in-memory vector backend，支持 upsert、search 和 delete。

#### Scenario: Upsert then search
- **WHEN** 调用 `upsert("id-1", "python debugging", namespace="mem:user-1")`
- **AND** 在同一 namespace 中搜索 `"python debug"`
- **THEN** search 结果包含 `id-1`

#### Scenario: Limit is respected
- **WHEN** namespace 中存在多条向量
- **AND** 调用 `search(..., limit=2)`
- **THEN** 最多返回 2 条结果

### Requirement: Namespace isolation
系统 SHALL 确保不同 namespace 的向量互相隔离。

#### Scenario: Search does not cross namespace
- **WHEN** namespace A 和 namespace B 中分别写入不同向量
- **AND** 调用方只搜索 namespace A
- **THEN** 返回结果不包含 namespace B 的 id

### Requirement: Upsert overwrite
系统 SHALL 以 namespace + id 作为唯一键；重复 upsert SHALL 覆盖旧向量。

#### Scenario: Upsert same id overwrites
- **WHEN** 同一 namespace 中用同一 id 写入旧文本后再写入新文本
- **THEN** 后续 search 使用新文本对应向量，不产生重复 id

### Requirement: Delete vector
系统 SHALL 支持按 namespace + id 删除向量。

#### Scenario: Delete removes vector
- **WHEN** 调用 `delete("id-1", namespace="mem:user-1")`
- **THEN** 后续 search 不再返回 `id-1`

### Requirement: Search ordering
系统 SHALL 按 score 降序返回 search 结果；score 相同时 SHALL 按 id 升序稳定排序。

#### Scenario: Results are sorted by score
- **WHEN** 多条结果被 search 命中
- **THEN** 返回顺序按 score 从高到低排列

#### Scenario: Equal scores are sorted by id
- **WHEN** 多条结果 score 相同
- **THEN** 返回顺序按 id 升序排列
