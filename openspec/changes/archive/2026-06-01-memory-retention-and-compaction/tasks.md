## 0. 前置确认

- [x] 0.1 确认本 change 只作用于 per-user semantic memory，不实现 Shared Memory
- [x] 0.2 确认本 change 不做 reflection 自动写回；`memory-reflection-maintenance` 后续单独处理
- [x] 0.3 确认本 change 不新增 scheduler、admin UI 或新持久表
- [x] 0.4 确认默认测试使用 tmp SQLite 和 mock vector_store，不调用真实 LLM / embedding

## 1. Public maintenance API

- [x] 1.1 Write failing tests: `MemoryMaintenancePolicy`、`MemoryMaintenanceSummary`、`MemoryCompactionCandidate`、`run_memory_maintenance()` 可从 `fleetent.memory_layer` 导入
- [x] 1.2 Write failing tests: empty user_id 和负数 limit fail fast
- [x] 1.3 Implement: public dataclasses and validation
- [x] 1.4 Verify green: 运行 `uv run pytest tests/unit/test_memory_retention_compaction.py -x -q`

## 2. Dry-run retention summary

- [x] 2.1 Write failing tests: dry-run 统计 expired context rows 但不删除 SQLite row
- [x] 2.2 Write failing tests: dry-run 统计 per-type over-limit rows 但不调用 vector_store.delete
- [x] 2.3 Implement: dry-run scan and summary
- [x] 2.4 Verify green: 运行 `uv run pytest tests/unit/test_memory_retention_compaction.py -x -q`

## 3. Apply retention cleanup

- [x] 3.1 Write failing tests: apply 删除 expired context rows
- [x] 3.2 Write failing tests: apply 按 type max count 删除 older over-limit rows
- [x] 3.3 Write failing tests: apply 删除时调用 `vector_store.delete(id, mem:{user_id})`
- [x] 3.4 Implement: retention cleanup and vector delete
- [x] 3.5 Verify green: 运行 `uv run pytest tests/integration/test_memory_retention_compaction.py -x -q`

## 4. Duplicate compaction

- [x] 4.1 Write failing tests: 同 user/type normalized duplicate 产生 `MemoryCompactionCandidate`
- [x] 4.2 Write failing tests: duplicate canonical item 选择 newest row
- [x] 4.3 Write failing tests: apply + compact_duplicates 删除 duplicate ids，不删除 canonical id
- [x] 4.4 Implement: deterministic duplicate grouping and apply
- [x] 4.5 Verify green: 运行 `uv run pytest tests/unit/test_memory_retention_compaction.py tests/integration/test_memory_retention_compaction.py -x -q`

## 5. Isolation and docs

- [x] 5.1 Write failing tests: user A maintenance 不读取或删除 user B memory
- [x] 5.2 Write failing tests: vector delete namespace 固定为 `mem:{user_id}`
- [x] 5.3 Implement: isolation fixes discovered by tests
- [x] 5.4 更新 `docs/capabilities/memory.md`
- [x] 5.5 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 5.6 运行相关 tests
- [x] 5.7 运行 `uv run ruff format src tests`
- [x] 5.8 运行 `uv run ruff check src tests`
- [x] 5.9 运行 `uv run mypy src`
- [x] 5.10 运行 `uv run pytest -x -q`
- [x] 5.11 运行 `openspec validate memory-retention-and-compaction --strict`
- [x] 5.12 运行 `git diff --check`
