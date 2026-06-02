## 0. 前置确认

- [x] 0.1 确认本 change 只拆分 memory package，不改 memory 行为
- [x] 0.2 确认不新增 Shared Memory
- [x] 0.3 确认不新增数据库 migration
- [x] 0.4 确认旧 `fleetent.memory_layer` 只保留 thin shim

## 1. Package skeleton and public API compatibility

- [x] 1.1 Write failing tests: `fleetent.intelligence.memory` package 可 import
- [x] 1.2 Write failing tests: canonical path 暴露现有 memory public API
- [x] 1.3 Write failing tests: legacy `fleetent.memory_layer` 与 canonical path 暴露同一 public API objects
- [x] 1.4 Implement: 新增 `intelligence/memory/` package skeleton 和 `__init__.py`
- [x] 1.5 Verify green: 运行 import compatibility tests

## 2. Split models and store

- [x] 2.1 Write failing tests: `models.py` 暴露 memory dataclasses 和 `MemoryType`
- [x] 2.2 Write failing tests: store helpers 保持既有 row mapping、snapshot、insert/update/delete 行为
- [x] 2.3 Implement: 迁移 dataclass / type 到 `models.py`
- [x] 2.4 Implement: 迁移 SQLite 读写和 datetime helper 到 `store.py`
- [x] 2.5 Verify green: 运行 `uv run pytest tests/integration/test_memory_layer.py tests/unit/test_memory_indexable_items.py -x -q`

## 3. Split extraction and search

- [x] 3.1 Write failing tests: `extract_and_update()` 通过 canonical path 保持 create/update/delete/ignore 行为
- [x] 3.2 Write failing tests: `search()` 通过 canonical path 保持 vector result ordering 和过期过滤行为
- [x] 3.3 Implement: 迁移 extraction workflow 到 `extraction.py`
- [x] 3.4 Implement: 迁移 semantic search 到 `search.py`
- [x] 3.5 Verify green: 运行 `uv run pytest tests/integration/test_memory_layer.py tests/evaluation/test_memory_extraction_eval.py -x -q`

## 4. Split operations and maintenance

- [x] 4.1 Write failing tests: update / stale / delete / merge public operations 行为保持不变
- [x] 4.2 Write failing tests: retention / compaction dry-run 和 apply 行为保持不变
- [x] 4.3 Implement: 迁移 public operations 到 `operations.py`
- [x] 4.4 Implement: 迁移 maintenance workflow 到 `maintenance.py`
- [x] 4.5 Verify green: 运行 `uv run pytest tests/unit/test_memory_retention_compaction.py tests/integration/test_memory_retention_compaction.py -x -q`

## 5. Shim, canonical imports, and docs

- [x] 5.1 Write failing tests: `fleetent.memory_layer` shim 不承载业务逻辑，并 re-export canonical public API
- [x] 5.2 Implement: 顶层 `memory_layer.py` 改为 thin shim
- [x] 5.3 Implement: 更新 intelligence 内部 import 到 `fleetent.intelligence.memory`
- [x] 5.4 更新 `docs/architecture/source-module-organization-roadmap.md`，标记 memory package migration 已有 implementation spec
- [x] 5.5 更新 OpenSpec `module-boundaries` 和 `memory-layer` 说明
- [x] 5.6 Verify green: 运行 memory、reflection、long-term context、vector reindex 相关测试

## 6. Final verification

- [x] 6.1 运行 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [x] 6.2 运行 `uv run ruff format src tests`
- [x] 6.3 运行 `uv run ruff check src tests`
- [x] 6.4 运行 `uv run mypy src`
- [x] 6.5 运行 `uv run pytest -x -q`
- [x] 6.6 运行 `openspec validate 2026-06-02-memory-layer-package-migration --strict`
- [x] 6.7 运行 `git diff --check`
