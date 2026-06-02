# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 memory-layer spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-shared-memory --strict`

## 2. Schema and models

- [x] 2.1 Write failing tests：Alembic upgrade 后存在 `shared_memory_items`，字段包含 scope/type/status/source/audit 时间字段
- [x] 2.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 2.3 Implement：新增 Alembic migration、`SharedMemoryItem` dataclass、type/status constants
- [x] 2.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 2.5 Write failing tests：非法 scope_type、type、status、空 content fail fast
- [x] 2.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.7 Implement：补 validation
- [x] 2.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Store and vector synchronization

- [x] 3.1 Write failing tests：create/update active item 写入 SQLite 并调用 `vector_store.upsert()` 到 `shared:{scope_type}:{scope_id}`
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 create/update store 和 vector sync
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 3.5 Write failing tests：archive item 后不再被 search 返回，并调用 `vector_store.delete()`
- [x] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.7 Implement：实现 archive
- [x] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Search and reindex boundary

- [x] 4.1 Write failing tests：`search_shared_memory()` 保持 scope isolation，并按 vector order 返回 active/stale item
- [x] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.3 Implement：实现 search
- [x] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing tests：`iter_indexable_shared_memories()` 返回 namespace/id/content，排除 archived item
- [x] 4.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.7 Implement：实现 reindex iterator
- [x] 4.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 5. Reflection proposal apply

- [x] 5.1 Write failing tests：approved shared memory proposal apply 后创建 Shared Memory，并记录 source/source_ref
- [x] 5.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.3 Implement：实现 proposal apply public API
- [x] 5.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 5.5 Write failing tests：非 approved、target 非 shared_memory 或 scope 非法的 proposal 不可 apply
- [x] 5.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 5.7 Implement：补 proposal guard
- [x] 5.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 6. Admin/API and evaluation

- [x] 6.1 Write failing tests：admin/CLI 可 list/create/update/archive shared memory，写操作有权限和审计
- [x] 6.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 6.3 Implement：新增最小维护入口
- [x] 6.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 6.5 Write failing tests：deterministic evaluation 覆盖 scope isolation、archived exclusion、proposal apply retrieval
- [x] 6.6 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [x] 6.7 Implement：新增 evaluation fixture / runner
- [x] 6.8 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 7. Documentation and verification

- [x] 7.1 Write failing tests：capability docs / roadmap 说明 Shared Memory 已有数据层，但不接 prompt 注入
- [x] 7.2 Verify red：运行相关文档测试
- [x] 7.3 Implement：更新 `docs/capabilities/memory.md`、`docs/capabilities/long-term-ctx.md` 和 `docs/capabilities/owner-capability-roadmap.md`
- [x] 7.4 Verify green：运行相关文档测试
- [x] 7.5 运行 `uv run ruff format src tests`
- [x] 7.6 运行 `uv run ruff check src tests`
- [x] 7.7 运行 `uv run mypy src`
- [x] 7.8 运行 `uv run pytest -x -q`
- [x] 7.9 运行 `openspec validate 2026-06-02-shared-memory --strict`
- [x] 7.10 运行 `git diff --check`
