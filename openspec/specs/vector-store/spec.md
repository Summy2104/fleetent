# vector-store Specification

## Purpose
Provide the shared vector index foundation used by memory and knowledge-base features to embed text,
store vectors by namespace, and retrieve the most similar ids without owning business data.
## Requirements
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
系统 SHALL 提供 vector store、embedding 和 rerank 配置默认值。当前版本 SHALL 默认使用
in-memory vector backend、deterministic embedding backend，并默认禁用 rerank。

#### Scenario: Default embedding config
- **WHEN** 未显式配置 embedding
- **THEN** `embedding.backend` 默认为 `deterministic`
- **AND** `embedding.dimensions` 默认为 64

#### Scenario: HTTP embedding config exists
- **WHEN** 读取默认 settings
- **THEN** embedding 配置包含 endpoint、model、api_key_env 和 timeout_seconds 字段

#### Scenario: Default rerank config
- **WHEN** 未显式配置 rerank
- **THEN** `rerank.backend` 默认为 `disabled`

#### Scenario: HTTP rerank config exists
- **WHEN** 读取默认 settings
- **THEN** rerank 配置包含 endpoint、model、api_key_env 和 timeout_seconds 字段

#### Scenario: Unsupported provider backend fails fast
- **WHEN** 配置了当前不支持的 vector、embedding 或 rerank backend
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

### Requirement: Embedding provider abstraction
系统 SHALL 提供可替换的 embedding provider，用于将文本转换为向量。

#### Scenario: Deterministic embedding remains default
- **WHEN** 使用默认配置创建 embedding provider
- **THEN** 系统使用 deterministic embedding provider

#### Scenario: HTTP embedding provider can be configured
- **WHEN** `embedding.backend="http"`
- **THEN** 系统创建 HTTP embedding provider

#### Scenario: HTTP embedding request shape
- **WHEN** HTTP embedding provider embed 非空文本
- **THEN** 系统向 configured endpoint 发送包含 model 和 input list 的请求
- **AND** `api_key_env` 非空且对应环境变量存在时发送 Authorization Bearer header

#### Scenario: HTTP embedding response shape
- **WHEN** HTTP embedding provider 收到 `data[0].embedding`
- **THEN** 返回该 embedding vector
- **AND** vector 维度必须等于 `embedding.dimensions`

#### Scenario: Empty text embedding avoids HTTP call
- **WHEN** HTTP embedding provider embed 空白文本
- **THEN** 不发送 HTTP 请求
- **AND** 返回指定维度的零向量

#### Scenario: HTTP embedding errors are explicit
- **WHEN** HTTP embedding 返回非 2xx、超时、malformed JSON、缺失 embedding 或维度不匹配
- **THEN** 系统抛出明确的 embedding provider error
- **AND** 不静默 fallback 到 deterministic embedding

### Requirement: Rerank provider abstraction
系统 SHALL 提供可替换的 rerank provider，用于后续 knowledge-base retrieval 对候选文档重排。

#### Scenario: Rerank result shape
- **WHEN** 调用方收到 `RerankResult`
- **THEN** 结果只包含原始 document index 和 score

#### Scenario: Rerank is disabled by default
- **WHEN** 使用默认 rerank 配置创建 provider
- **THEN** 系统创建 disabled rerank provider
- **AND** 调用 rerank 时明确失败

#### Scenario: Deterministic rerank provider exists for tests
- **WHEN** `rerank.backend="deterministic"`
- **THEN** 系统创建 deterministic rerank provider
- **AND** 相同输入返回稳定结果

#### Scenario: HTTP rerank request shape
- **WHEN** HTTP rerank provider rerank documents
- **THEN** 系统向 configured endpoint 发送 model、query、documents 和 top_n
- **AND** `api_key_env` 非空且对应环境变量存在时发送 Authorization Bearer header

#### Scenario: HTTP rerank response shape
- **WHEN** HTTP rerank provider 收到 `results[{index, score}]`
- **THEN** 返回按 provider 输出顺序排列的 `RerankResult`

#### Scenario: HTTP rerank errors are explicit
- **WHEN** HTTP rerank 返回非 2xx、超时、malformed JSON、越界 index 或非数字 score
- **THEN** 系统抛出明确的 rerank provider error
- **AND** 不静默 fallback 到 deterministic rerank

### Requirement: Vector store runtime uses embedding provider
`vector_store.upsert()` 和 `vector_store.search()` SHALL 使用配置的 embedding provider，
但 public API 保持不变。

#### Scenario: Upsert embeds through configured provider
- **WHEN** 调用 `vector_store.upsert(id, text, namespace)`
- **THEN** 系统通过配置的 embedding provider 生成向量
- **AND** 将向量写入 vector backend

#### Scenario: Search embeds through configured provider
- **WHEN** 调用 `vector_store.search(query, namespace, limit)`
- **THEN** 系统通过配置的 embedding provider 生成 query 向量
- **AND** 使用该向量查询 vector backend
