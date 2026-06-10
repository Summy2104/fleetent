## 1. Fix asyncio.run() in test_vector_store_reindex.py

- [ ] 1.1 (test) 确认两个测试当前是 `def`（同步），运行 `uv run pytest tests/integration/test_vector_store_reindex.py -x -q` 看绿（基线）
- [ ] 1.2 将 `test_memory_rebuild_removes_stale_vectors_and_indexes_current_items` 改为 `async def`，把所有 `asyncio.run(upsert(...))` / `asyncio.run(search(...))` 改为 `await upsert(...)` / `await search(...)`；`reindex()` 保持直接调用（同步）
- [ ] 1.3 将 `test_knowledge_base_rebuild_removes_stale_vectors_and_indexes_current_chunks` 同样改为 `async def`，改写所有 `asyncio.run(...)` 调用
- [ ] 1.4 移除文件顶部 `import asyncio`（不再需要）
- [ ] 1.5 运行 `uv run pytest tests/integration/test_vector_store_reindex.py -x -q` 确认绿

## 2. Bulk INSERT in test_memory_layer.py

- [ ] 2.1 (test) 运行 `uv run pytest tests/integration/test_memory_layer.py::test_extract_and_update_limits_snapshot_and_excludes_expired_context -x -q` 看绿（基线）
- [ ] 2.2 在 `test_memory_layer.py` 中新增 `_insert_memory_rows(db_path, rows: list[dict])` 函数，使用单次 `sqlite3.connect` + `conn.executemany`，参数结构与 `_insert_memory_row` 一致
- [ ] 2.3 将 `test_extract_and_update_limits_snapshot_and_excludes_expired_context` 中三段循环（25 identity + 35 preference + 25 context）改为调用 `_insert_memory_rows`
- [ ] 2.4 运行 `uv run pytest tests/integration/test_memory_layer.py::test_extract_and_update_limits_snapshot_and_excludes_expired_context -x -q` 确认绿
- [ ] 2.5 运行 `uv run pytest tests/integration/test_memory_layer.py -x -q` 确认全文件绿

## 3. Module-scoped client fixture — test_stats_admin_api.py

- [ ] 3.1 (test) 运行 `uv run pytest tests/integration/test_stats_admin_api.py -x -q` 看绿（基线）
- [ ] 3.2 将 `client` fixture 改为 `scope="module"`，用 `tmp_path_factory` 替代 `tmp_path`，用手动实例化 `pytest.MonkeyPatch()` 替代 `monkeypatch` 参数，在 `yield` 后调用 `mp.undo()`
- [ ] 3.3 检查每个测试函数是否在 test body 内用 `monkeypatch` 做额外 patch（如 `fetch_traces`）；这些 test-level patch 不受影响（仍是 function-scoped monkeypatch）
- [ ] 3.4 运行 `uv run pytest tests/integration/test_stats_admin_api.py -x -q` 确认绿

## 4. Module-scoped client fixture — test_provider_admin_api.py

- [ ] 4.1 (test) 运行 `uv run pytest tests/integration/test_provider_admin_api.py -x -q` 看绿（基线）
- [ ] 4.2 将 `client` fixture 改为 `scope="module"`，同 task 3.2 的方式
- [ ] 4.3 检查写测试（`test_add_provider_*`、`test_route_order_set_and_reorder` 等）：这些测试写入共享 DB；评估是否需要拆出独立 function-scoped `fresh_client` fixture；写测试之间若无顺序依赖可接受共享状态
- [ ] 4.4 运行 `uv run pytest tests/integration/test_provider_admin_api.py -x -q` 确认绿

## 5. Module-scoped client fixture — test_agent_admin_api.py

- [ ] 5.1 (test) 运行 `uv run pytest tests/integration/test_agent_admin_api.py -x -q` 看绿（基线）
- [ ] 5.2 将 `client` fixture 改为 `scope="module"`，同 task 3.2 的方式
- [ ] 5.3 运行 `uv run pytest tests/integration/test_agent_admin_api.py -x -q` 确认绿

## 6. 收尾验证

- [ ] 6.1 运行 `make test-pr` 确认无新增失败（对照 main 基线：约 2 unit + 若干 integration 预先存在失败）
- [ ] 6.2 运行 `uv run pytest tests/integration -q`（不带 `-x`）确认 integration 无新增失败
