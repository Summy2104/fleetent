## Why

memory、knowledge-base 和 long-term-ctx 都依赖向量检索，但当前项目还没有统一的 vector_store
contract。若直接在 memory 或 knowledge-base 中各自实现 embedding / 相似度 / namespace 隔离，后续会出现
重复实现、接口不一致和后端切换困难。

本 change 先建立 vector_store foundation：稳定 public API、namespace helper、deterministic
embedding 和 in-memory backend。目标是给上层模块提供可测试的共同地基，而不是一次性引入生产级向量数据库。

## What Changes

- 新增 `vector-store` 能力规范。
- 新增 `fleetent.intelligence.vector_store` package。
- 提供 public API：
  - `SearchResult`
  - `upsert(id, text, namespace)`
  - `search(query, namespace, limit=10)`
  - `delete(id, namespace)`
  - `memory_namespace(user_id)`
  - `knowledge_namespace(tenant_id, kb_id)`
- 新增 deterministic embedding backend，用于测试和本地开发。
- 新增 in-memory vector backend，支持 namespace 隔离、upsert 覆盖、delete、score 降序。
- 新增配置命名空间：
  - `vector_store.backend`
  - `embedding.backend`
- 默认仅支持 `vector_store.backend="memory"` 和 `embedding.backend="deterministic"`。

## Capabilities

### New Capabilities

- `vector-store`：统一向量索引基础设施，提供 embedding、namespace 隔离、向量写入、检索和删除 contract。

### Modified Capabilities

- 无。本 change 不接入 memory_layer、knowledge_base 或 long_term_ctx。

## Impact

- **代码**：
  - 新增 `src/fleetent/intelligence/vector_store/`。
  - 新增可配置的 vector store runtime / backend factory。
  - 新增 deterministic embedding 与 in-memory backend。
  - 顶层旧路径无需 shim，因为当前没有既有 `fleetent.vector_store` public API。
- **配置**：
  - 增加 `vector_store` 与 `embedding` 默认配置。
- **测试**：
  - 覆盖 namespace helper、upsert/search/delete、score 排序、backend 配置错误。
- **不包含**：
  - 不接 sqlite-vec。
  - 不接 Qdrant。
  - 不加载 bge-m3 / multilingual-e5。
  - 不接 HTTP embedding sidecar。
  - 不做持久化。
  - 不修改 memory_layer / knowledge_base / long_term_ctx。
