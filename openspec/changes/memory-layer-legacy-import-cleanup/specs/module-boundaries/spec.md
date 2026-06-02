## MODIFIED Requirements

### Requirement: Memory layer package migration
系统 SHALL expose User Memory implementation through `fleetent.intelligence.memory` canonical package paths
only; the legacy `fleetent.memory_layer` shim SHALL NOT remain importable.

#### Scenario: Memory canonical package exists
- **WHEN** 调用方导入 `fleetent.intelligence.memory`
- **THEN** 导入成功

#### Scenario: Memory canonical package exports public API
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `MemoryItem`、`MemoryType`、`extract_and_update`、`search`、public operations 或 `run_memory_maintenance`
- **THEN** 导入成功
- **AND** public object 行为与迁移前保持一致

#### Scenario: Legacy memory import is removed
- **WHEN** 调用方导入 `fleetent.memory_layer`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Memory package owns memory items data access
- **WHEN** memory 功能访问既有 `memory_items` table
- **THEN** 该访问由 `fleetent.intelligence.memory.store` 实现负责
- **AND** 本 change 不新增或修改数据库 schema

#### Scenario: Memory canonical submodules separate responsibilities
- **WHEN** 查看 `fleetent.intelligence.memory` package
- **THEN** 数据模型位于 `models.py`
- **AND** SQLite store 位于 `store.py`
- **AND** LLM extraction 位于 `extraction.py`
- **AND** semantic search 位于 `search.py`
- **AND** public operations 位于 `operations.py`
- **AND** retention / compaction maintenance 位于 `maintenance.py`

#### Scenario: Intelligence modules use memory through public API
- **WHEN** long-term context、reflection 或 vector reindex 需要读取 User Memory
- **THEN** 它们通过 `fleetent.intelligence.memory` public API 调用 memory 能力
- **AND** memory package 不反向 import runtime entrypoint
