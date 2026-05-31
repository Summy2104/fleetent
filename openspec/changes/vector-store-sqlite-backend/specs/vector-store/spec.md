## MODIFIED Requirements

### Requirement: Vector store configuration
系统 SHALL 提供 vector store、embedding 和 rerank 配置默认值。当前版本 SHALL 默认使用
in-memory vector backend、deterministic embedding backend，并默认禁用 rerank。

#### Scenario: SQLite vector backend can be configured
- **WHEN** `vector_store.backend="sqlite"`
- **THEN** 系统创建 SQLite persistent vector backend

#### Scenario: SQLite backend database URL default
- **WHEN** `vector_store.backend="sqlite"` 且未配置 `vector_store.database_url`
- **THEN** SQLite vector backend 使用全局 `Settings.database_url`

#### Scenario: SQLite backend rejects unsupported database URL
- **WHEN** `vector_store.backend="sqlite"` 且 database_url 不是本地 sqlite URL
- **THEN** 系统 fail fast，并说明只支持本地 sqlite URL

#### Scenario: Unsupported vector backend fails fast
- **WHEN** 配置了当前不支持的 vector backend
- **THEN** 初始化失败，并明确说明当前支持的 backend

## ADDED Requirements

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
