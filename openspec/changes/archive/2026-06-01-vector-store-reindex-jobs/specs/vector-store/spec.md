## ADDED Requirements

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
