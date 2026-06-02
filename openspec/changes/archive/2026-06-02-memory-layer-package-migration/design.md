## Context

`memory_layer.py` 当前承担了一个完整 memory 子系统，但所有职责在一个文件中：

| 职责 | 当前内容 | 目标模块 |
| --- | --- | --- |
| 数据模型 | `MemoryItem`、`MemoryMaintenancePolicy`、summary / candidate dataclass | `models.py` |
| Store | `_database()`、insert / update / delete / snapshot / row parsing | `store.py` |
| Extraction | `extract_and_update()`、prompt、action filtering、conversation serialization | `extraction.py` |
| Search | vector search 后回表过滤 non-expired memory | `search.py` |
| Operations | update / stale / delete / merge / indexable iterator | `operations.py` |
| Maintenance | retention、over-limit、duplicate compaction | `maintenance.py` |

本 change 的目标是让后续 memory 功能有清晰落点，而不是一次性重新设计 memory 模型。

## Target Structure

目标结构：

```text
src/fleetent/intelligence/memory/
  __init__.py
  models.py
  store.py
  extraction.py
  search.py
  maintenance.py
  operations.py

src/fleetent/memory_layer.py
```

`src/fleetent/memory_layer.py` 只保留 compatibility shim。

## Module Responsibilities

### `models.py`

负责纯数据结构和类型：

- `MemoryType`
- `MemoryItem`
- `MemoryMaintenancePolicy`
- `MemoryCompactionCandidate`
- `MemoryMaintenanceSummary`

不访问数据库，不调用 LLM，不调用 vector store。

### `store.py`

负责 `memory_items` 的 SQLite 读写和 row mapping：

- `get_user_memory()`
- `insert_memory()`
- `update_memory()`
- `delete_memory()`
- `memory_snapshot()`
- `memory_snapshot_by_type()`
- `expired_context_ids()`
- `over_limit_ids()`
- `duplicate_compaction_candidates()`
- datetime formatting / parsing helper

可以继续使用现有 `Settings(...).database_url` 和 `create_database()`，不在本 change 中重写 database runtime。

### `extraction.py`

负责 LLM extraction workflow：

- `extract_and_update()`
- extraction system prompt。
- markdown fence stripping。
- action 校验。
- `_targets_non_user_memory()`。
- conversation serialization。

extraction 调用 `store.py` 写入 memory，并调用 `vector_store` 维护向量索引。prompt 文案和 action 语义保持不变。

### `search.py`

负责 public `search()`：

- 调用 `vector_store.search()`。
- 根据结果 id 回表读取 `memory_items`。
- 过滤过期 memory。
- 保持返回顺序与 vector result 顺序一致。

### `operations.py`

负责用户级 memory 操作：

- `update_user_memory_content()`
- `mark_user_memory_stale()`
- `delete_user_memory()`
- `merge_user_memories()`
- `iter_indexable_memories()`

这些函数调用 `store.py` 和 `vector_store`，不直接处理 extraction prompt。

### `maintenance.py`

负责 public `run_memory_maintenance()`：

- validate policy。
- expired context cleanup。
- over-limit cleanup。
- duplicate compaction。
- dry-run / apply。

维护策略和删除顺序保持不变。

## Public API Strategy

新 canonical import：

```python
from fleetent.intelligence.memory import MemoryItem, search, extract_and_update
```

旧 import 继续可用：

```python
from fleetent.memory_layer import MemoryItem, search, extract_and_update
```

`fleetent.memory_layer` shim 不允许：

- 创建数据库连接。
- 调用 LLM。
- 调用 vector store。
- 承载 memory 业务逻辑。
- 定义可变运行时状态。

如果测试需要 monkeypatch internal helper，优先迁移到 `fleetent.intelligence.memory.*` 的具体模块路径。

## Import Migration

建议优先更新：

- `intelligence.long_term_ctx` 使用 `fleetent.intelligence.memory`。
- `intelligence.reflection` 使用 `fleetent.intelligence.memory`。
- `intelligence.vector_store.reindex` 使用 `fleetent.intelligence.memory`。
- 新增测试使用 canonical path。

legacy tests 可以继续验证 `fleetent.memory_layer` compatibility，但不应新增对 shim internal helper 的依赖。

## Risks

- 拆分时 public API re-export 漏项。
- circular import：`extraction.py`、`operations.py`、`maintenance.py` 都会依赖 `store.py` 和 `models.py`，应避免 `store.py` 反向 import 这些高层模块。
- vector store namespace 误改会影响 reindex 和 search。
- memory DB monkeypatch 如果依赖旧 private helper，迁移后需要改到具体 canonical 模块。
- extraction prompt 顺手调整会改变评估结果，应避免。

## Verification

必须验证：

- 新 canonical import 可用。
- 旧 `fleetent.memory_layer` import 可用。
- memory layer integration tests 通过。
- memory retention / compaction tests 通过。
- memory reflection maintenance tests 通过。
- long-term context / reflection tests 通过。
- vector reindex indexable memory tests 通过。
- module boundary check 通过。
- 完整测试通过。
