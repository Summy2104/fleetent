## ADDED Requirements

### Requirement: Memory layer package migration
系统 SHALL 将 User Memory 实现迁入 `fleetent.intelligence.memory` package，并保持 legacy `fleetent.memory_layer` import 路径兼容。

#### Scenario: Memory canonical package exists
- **WHEN** 调用方导入 `fleetent.intelligence.memory`
- **THEN** 导入成功

#### Scenario: Memory canonical package exposes public API
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 memory public API
- **THEN** `MemoryItem`、`MemoryType`、`extract_and_update()`、`search()`、public operations 和 `run_memory_maintenance()` 可用

#### Scenario: Legacy memory import remains compatible
- **WHEN** 调用方导入 `fleetent.memory_layer`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前的 memory public API

#### Scenario: Memory shim does not contain business logic
- **WHEN** 查看 legacy 顶层 `memory_layer.py`
- **THEN** 文件只 re-export `fleetent.intelligence.memory` 的 public names
- **AND** 不访问数据库
- **AND** 不调用 LLM
- **AND** 不调用 vector store
- **AND** 不承载 memory 业务逻辑

#### Scenario: Memory package owns memory items data access
- **WHEN** memory 功能访问既有 `memory_items` table
- **THEN** 该访问由 `fleetent.intelligence.memory` package 内的 store 实现负责
- **AND** 本 change 不新增或修改数据库 schema

#### Scenario: Intelligence modules use memory through public API
- **WHEN** long-term context、reflection 或 vector reindex 需要读取 User Memory
- **THEN** 它们通过 `fleetent.intelligence.memory` public API 调用 memory 能力
- **AND** memory package 不反向 import runtime entrypoint
