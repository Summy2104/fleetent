## Why

`src/fleetent/memory_layer.py` 当前已经增长到 600+ 行，并混合了多类职责：

- User Memory 数据模型。
- SQLite store 读写。
- LLM memory extraction。
- vector store search / reindex support。
- retention、compaction、merge、stale、delete 等维护操作。

memory 是 intelligence 域后续 shared memory、reflection maintenance、long-term context evaluation 和 reindex
job 的核心依赖。如果继续保留单个平铺文件，后续功能会继续堆叠在同一文件里，容易形成冲突热点，也不利于 public
API 边界收敛。

本 change 只做结构拆分：把 memory 实现迁入 `fleetent.intelligence.memory` package，并保留
`fleetent.memory_layer` thin shim。行为、schema、retention 策略、vector namespace 和 extraction 语义保持不变。

## What Changes

- 新增 `src/fleetent/intelligence/memory/` package。
- 将 `memory_layer.py` 拆分为：
  - `models.py`
  - `store.py`
  - `extraction.py`
  - `search.py`
  - `maintenance.py`
  - `operations.py`
- `src/fleetent/intelligence/memory/__init__.py` re-export memory public API。
- `src/fleetent/memory_layer.py` 改为 compatibility shim，只 re-export public API。
- 更新 intelligence 内部明显属于 memory 的 import 到 canonical path。
- 增加或调整测试，证明新 canonical import 和旧 import 路径都可用。
- 更新 source module organization roadmap，记录 memory package migration spec。

## Out of Scope

- 不新增 Shared Memory。
- 不修改 `memory_items` schema。
- 不新增 Alembic migration。
- 不修改 `MemoryType` 取值。
- 不修改 context TTL。
- 不修改 extraction prompt 语义。
- 不修改 vector store namespace。
- 不修改 retention / compaction 策略。
- 不修改 reflection 或 long-term context 行为。
- 不重写 database runtime 或引入 repository 抽象。
- 不删除旧 `fleetent.memory_layer` import shim。

## Module Boundary Impact

- **Owning package**：`intelligence.memory`。
- **Public API surface**：
  - 新增 canonical import 路径 `fleetent.intelligence.memory`。
  - 保留 legacy import 路径 `fleetent.memory_layer`。
  - public names 包括 `MemoryType`、`MemoryItem`、`MemoryMaintenancePolicy`、
    `MemoryCompactionCandidate`、`MemoryMaintenanceSummary`、`extract_and_update`、`search`、
    `update_user_memory_content`、`mark_user_memory_stale`、`delete_user_memory`、
    `merge_user_memories`、`iter_indexable_memories`、`run_memory_maintenance`。
- **Owned tables**：既有 `memory_items` table owner 迁移为 `intelligence.memory`；不新增或修改 schema。
- **Config namespace**：无新增配置。
- **Cross-module dependencies**：
  - memory 继续依赖 `config` / `db` legacy infrastructure、`model_router` 和 `intelligence.vector_store` public API。
  - long-term context、reflection、vector reindex 可以通过 `fleetent.intelligence.memory` public API 使用 memory。
  - memory package 不 import runtime entrypoint。
- **Migration / shim plan**：
  - 第一步创建 `fleetent.intelligence.memory` package 并迁移实现。
  - 第二步在 `__init__.py` 暴露 public API。
  - 第三步将旧 `fleetent.memory_layer` 改为 thin shim。
  - 第四步更新新代码和 intelligence 内部 import 到 canonical path；不要求一次性消除所有 legacy tests import。
