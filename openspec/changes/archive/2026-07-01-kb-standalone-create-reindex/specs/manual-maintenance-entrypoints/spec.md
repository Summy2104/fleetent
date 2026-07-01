## MODIFIED Requirements

### Requirement: Public API boundaries

Manual maintenance entrypoints SHALL call owner module public APIs rather than importing internal implementation
details. Vector 索引重建不再作为平台维护命令提供(原 `platform maintenance vector reindex` 为 no-op 空壳,已退役);真向量重建改由 standalone `fleetent kb reindex` 入队、kb-worker 经 `vector_store` 公共 reindex API 执行(见 kb-standalone-ingest / kb-ingest-worker)。

#### Scenario: Memory compaction uses memory public API
- **WHEN** memory compaction is run from the platform maintenance CLI
- **THEN** it calls the memory module public API (not internal implementation)
- **AND** reports affected counts before mutation
