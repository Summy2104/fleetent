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

#### Scenario: SQLite vector backend can be configured
- **WHEN** `vector_store.backend="sqlite"`
- **THEN** 系统创建 SQLite persistent vector backend

#### Scenario: SQLite backend database URL default
- **WHEN** `vector_store.backend="sqlite"` 且未配置 `vector_store.database_url`
- **THEN** SQLite vector backend 使用全局 `Settings.database_url`
- **AND** backend 接收 runtime 解析后的 effective database URL
- **AND** backend 内部不重新创建 `Settings`

#### Scenario: SQLite backend rejects unsupported database URL
- **WHEN** `vector_store.backend="sqlite"` 且 database_url 不是本地 sqlite URL
- **THEN** 系统 fail fast，并说明只支持本地 sqlite URL

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

### Requirement: SQLite persistent vector backend
系统 SHALL 提供普通 SQLite persistent vector backend，持久化 namespace-scoped vectors。

#### Scenario: SQLite backend initializes schema
- **WHEN** SQLite backend 首次使用
- **THEN** 数据库包含 vector_store-owned `vector_items` 表
- **AND** 表包含 namespace、id、dimensions、vector_json 和 updated_at 字段

#### Scenario: SQLite backend persists vectors
- **WHEN** 一个 backend upsert vector 后进程内重新创建 backend
- **THEN** 新 backend 可以 search 到已写入的 id

#### Scenario: SQLite backend overwrites same id
- **WHEN** 同一 namespace + id 被重复 upsert
- **THEN** 后一次 vector 覆盖前一次
- **AND** 不产生重复记录

#### Scenario: SQLite backend keeps namespace isolation
- **WHEN** 不同 namespace 中写入相同或相似 vector
- **THEN** search 只返回查询 namespace 内的结果

#### Scenario: SQLite backend delete is namespace scoped
- **WHEN** 删除 namespace A 中的 id
- **THEN** namespace A 不再返回该 id
- **AND** namespace B 中相同 id 不受影响

#### Scenario: SQLite backend respects limit
- **WHEN** 调用 search 且 limit > 0
- **THEN** 返回结果数量不超过 limit
- **AND** limit <= 0 时返回空结果

### Requirement: SQLite backend similarity and data validation
SQLite backend SHALL 使用 Python cosine similarity 搜索同 namespace vectors，并对异常记录容错。

#### Scenario: SQLite search ordering is stable
- **WHEN** 多条 vector 被 search 命中
- **THEN** 结果按 score DESC 排序
- **AND** score 相同时按 id ASC 排序

#### Scenario: SQLite search skips dimension mismatch
- **WHEN** 存储记录的 dimensions 与 query vector 维度不一致
- **THEN** search 跳过该记录
- **AND** 继续返回其他合法结果

#### Scenario: SQLite search skips corrupt vector JSON
- **WHEN** 存储记录的 vector_json 损坏或不是数字数组
- **THEN** search 跳过该记录
- **AND** 继续返回其他合法结果

#### Scenario: SQLite upsert rejects empty vector
- **WHEN** 调用 upsert 且 vector 为空
- **THEN** 系统 fail fast

### Requirement: Vector backend adapter boundary
vector_store SHALL 通过 backend adapter 支持 memory 与 SQLite backend，并为后续 sqlite-vec、Qdrant
或 OpenSearch / Elasticsearch vector adapter 保留扩展边界。

#### Scenario: Public vector store API remains unchanged
- **WHEN** 切换 vector_store backend
- **THEN** `vector_store.upsert()`、`vector_store.search()` 和 `vector_store.delete()` public API 不变

#### Scenario: SQLite backend does not implement lexical search
- **WHEN** 使用 SQLite vector backend
- **THEN** backend 只负责 vector persistence 和 similarity search
- **AND** 不实现 BM25、metadata aggregation 或 knowledge-base hybrid search

### Requirement: Vector namespace clearing
系统 SHALL 提供 `clear_namespace(namespace)` public API，用于删除指定 namespace 下的所有 vector entries。

#### Scenario: Clear namespace API is importable
- **WHEN** 调用方从 `fleetent.intelligence.vector_store` 导入 `clear_namespace`
- **THEN** 导入成功

#### Scenario: Clear namespace removes only target namespace
- **WHEN** namespace A 和 namespace B 都存在 vectors
- **AND** 调用 `clear_namespace(namespace_a)`
- **THEN** 后续 search namespace A 不返回旧 vectors
- **AND** 后续 search namespace B 仍可返回 namespace B 的 vectors

#### Scenario: Clear namespace is idempotent
- **WHEN** 调用 `clear_namespace()` 清理空 namespace 或重复清理同一 namespace
- **THEN** 系统不报错

### Requirement: Indexable item shape
系统 SHALL 提供 `IndexableItem` dataclass，作为可重新写入 vector_store 的 source record 形状。

#### Scenario: IndexableItem API is importable
- **WHEN** 调用方从 `fleetent.intelligence.vector_store` 导入 `IndexableItem`
- **THEN** 导入成功

#### Scenario: IndexableItem fields
- **WHEN** 调用方构造 `IndexableItem`
- **THEN** item 包含 id、content、namespace 和 metadata

### Requirement: Reindex public API
系统 SHALL 提供同步 `reindex(ReindexRequest) -> ReindexSummary` public API，用于从 source of truth 重建 vector namespace。

#### Scenario: Reindex API is importable
- **WHEN** 调用方从 `fleetent.intelligence.vector_store` 导入 `ReindexRequest`、`ReindexSummary` 和 `reindex`
- **THEN** 导入成功

#### Scenario: Reindex summary shape
- **WHEN** 调用方收到 `ReindexSummary`
- **THEN** summary 包含 owner、namespace、dry_run、scanned、reindexed、skipped 和 failed

#### Scenario: Unsupported reindex request fails fast
- **WHEN** request 包含不支持的 owner、未知 mode、memory owner 缺少 user_id 或 knowledge_base owner 缺少 kb_id
- **THEN** 系统 fail fast，并给出明确错误

### Requirement: Reindex dry run
系统 SHALL 支持 dry-run reindex，用于统计将被重建的 source records 而不修改 vector index。

#### Scenario: Dry run scans memory source records
- **WHEN** 调用 `reindex(ReindexRequest(owner="memory", user_id="user-1", dry_run=True))`
- **THEN** summary 返回 memory namespace 和 scanned 计数
- **AND** 系统不调用 `clear_namespace()` 或 `upsert()`

#### Scenario: Dry run scans knowledge-base source records
- **WHEN** 调用 `reindex(ReindexRequest(owner="knowledge_base", tenant_id="default", kb_id="global", dry_run=True))`
- **THEN** summary 返回 knowledge namespace 和 scanned 计数
- **AND** 系统不调用 `clear_namespace()` 或 `upsert()`

### Requirement: Memory vector rebuild
系统 SHALL 支持从 memory public indexable iterator 重建指定用户的 memory vector namespace。

#### Scenario: Memory rebuild clears namespace first
- **WHEN** 调用 memory rebuild
- **THEN** 系统先调用 `clear_namespace(memory_namespace(user_id))`

#### Scenario: Memory rebuild upserts current memories
- **WHEN** memory rebuild 扫描到多个 indexable memory items
- **THEN** 系统为每个 item 调用 `upsert(item.id, item.content, item.namespace)`
- **AND** summary 返回 scanned、reindexed、skipped 和 failed 计数

#### Scenario: Memory rebuild continues after item failure
- **WHEN** 某个 memory item upsert 失败
- **THEN** summary.failed 增加
- **AND** 系统继续处理后续 items

### Requirement: Knowledge-base vector rebuild
系统 SHALL 支持从 knowledge-base public indexable iterator 重建指定 tenant/kb 的 vector namespace。

#### Scenario: Knowledge-base rebuild clears namespace first
- **WHEN** 调用 knowledge-base rebuild
- **THEN** 系统先调用 `clear_namespace(knowledge_namespace(tenant_id, kb_id))`

#### Scenario: Knowledge-base rebuild upserts current chunks
- **WHEN** knowledge-base rebuild 扫描到多个 indexable chunks
- **THEN** 系统为每个 item 调用 `upsert(item.id, item.content, item.namespace)`
- **AND** summary 返回 scanned、reindexed、skipped 和 failed 计数

#### Scenario: Knowledge-base rebuild continues after item failure
- **WHEN** 某个 chunk upsert 失败
- **THEN** summary.failed 增加
- **AND** 系统继续处理后续 items

### Requirement: Reindex excludes background job runtime
reindex SHALL remain a synchronous public API and SHALL NOT introduce persistent job tracking or background runtime.

#### Scenario: No job persistence is required
- **WHEN** reindex change 完成
- **THEN** 系统不新增 `reindex_jobs` 或 `reindex_items` 持久表

#### Scenario: No scheduler or worker dependency
- **WHEN** reindex change 完成
- **THEN** 系统不要求新增 scheduler、queue、worker、admin API 或 dashboard
