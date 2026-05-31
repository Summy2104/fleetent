## Why

`vector_store` foundation 当前只有 in-memory backend。它能验证 namespace、upsert、delete 和相似度排序，
但进程重启后向量全部丢失，无法支撑 memory 和 knowledge-base 的真实 MVP 闭环。

本 change 新增普通 SQLite persistent vector backend：向量以 JSON 存储，检索时在 Python 内做 cosine
similarity。它不依赖 sqlite-vec native extension，优先解决持久化和部署稳定性，为后续 sqlite-vec、
Qdrant、OpenSearch / Elasticsearch adapter 留出边界。

## What Changes

- 新增 `vector_store.backend = "sqlite"`。
- 新增可选 `vector_store.database_url`：
  - 未配置时复用全局 `Settings.database_url`。
  - 配置时必须是本地 `sqlite:///...` URL。
- 新增 SQLite backend owned storage：
  - `vector_items(namespace TEXT, id TEXT, dimensions INTEGER, vector_json TEXT, updated_at DATETIME)`
  - 唯一键：`namespace + id`
  - 索引：`namespace`
- 支持现有 backend contract：
  - `upsert(id, vector, namespace)`：插入或覆盖。
  - `search(vector, namespace, limit)`：只在同 namespace 内搜索，按 score DESC、id ASC 排序。
  - `delete(id, namespace)`：删除指定 namespace + id。
- 维度规则：
  - 写入时保存 vector 维度。
  - search 时只比较与 query vector 维度一致的记录。
  - 发现 vector_json 损坏或维度不匹配的记录时跳过该记录，不影响其他结果。
- 不改变 `vector_store.upsert()` / `search()` / `delete()` public API。
- 不引入 sqlite-vec、Qdrant、OpenSearch / Elasticsearch 或 ANN 检索。

## Design Notes

第一版使用 SQLite + Python cosine，而不是 sqlite-vec：

- 避免 native extension 的安装、CI 和 on-premises 平台兼容问题。
- 当前 MVP 更需要重启后不丢索引，而不是大规模 ANN 性能。
- adapter 边界保持不变，后续可新增 `sqlite_vec` 或 `qdrant` backend。

OpenSearch / Elasticsearch 后续更适合作为 knowledge-base 的 lexical / hybrid search backend。
本 change 只做 vector_store 的持久化 vector backend，不把 BM25、metadata filter、aggregation 放进
vector_store。

## Module Boundary Impact

- **owning package**：`intelligence.vector_store`。
- **public API surface**：`upsert()` / `search()` / `delete()` 不变；扩展 backend factory 内部能力。
- **owned tables**：`vector_items` 由 vector_store SQLite backend owns。
- **config namespace**：扩展 `vector_store.*`，新增 `vector_store.database_url`。
- **cross-module dependencies**：继续只依赖 config 和 database runtime；不依赖 memory / knowledge-base。
- **migration / shim plan**：无 Alembic migration；SQLite backend 启动或首次使用时自建 backend-owned table。

## Impact

- **代码**：
  - 扩展 `VectorStoreSettings`。
  - 新增 SQLite vector backend。
  - 调整 backend factory / runtime，让 sqlite backend 能获取 database_url。
- **测试**：
  - 覆盖持久化、namespace 隔离、overwrite、delete、limit、排序、维度处理、损坏数据跳过。
  - 使用 tmp SQLite DB，不触碰 `data/`。
- **数据**：新增 vector_store-owned SQLite 表；不迁移 in-memory 向量。
- **不包含**：
  - 不引入 sqlite-vec native extension。
  - 不实现 Qdrant backend。
  - 不实现 OpenSearch / Elasticsearch adapter。
  - 不做 retrieval quality evaluation。
  - 不接入 knowledge-base hybrid search。
