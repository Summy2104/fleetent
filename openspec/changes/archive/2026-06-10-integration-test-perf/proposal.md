## Why

集成测试套件墙钟时间过长，主要源于四个可静态识别的低效点：migration 重复执行、`asyncio.run()` 反复创建 event loop、API fixture 每 test 全量重建、以及循环单行 INSERT。这些问题不涉及业务逻辑，纯属测试基础设施开销，修复后预计整体集成测试速度提升 30–50%。

## What Changes

- **消除同步函数内的 `asyncio.run()`**：`test_vector_store_reindex.py` 两个测试函数内有 10 次 `asyncio.run()` 调用，改为 `async def` 测试（项目已配置 `asyncio_mode = auto`，无需额外 mark）。
- **API fixture 提升 scope**：`test_agent_admin_api.py`（30 tests）、`test_stats_admin_api.py`（13 tests）、`test_provider_admin_api.py`（23 tests）等高频 API 测试文件的 `client` fixture 从 `scope="function"` 改为 `scope="module"`；以 `pytest.MonkeyPatch()` + `tmp_path_factory` 替代 `monkeypatch` 参数绕过 scope 限制。
- **批量 INSERT 替代循环单行写**：`test_memory_layer.py` 三段 85 次循环单连接 INSERT 改为单次 `executemany`。

> **注**：初始分析提到「migration 导入路径分裂」问题，经核查 `test_migrations.py` 已 re-export `apply_migrations` 自 `_migration_template`（带 `lru_cache`），该路径已正确缓存，无需修改。

## Capabilities

### New Capabilities

- `integration-test-perf`: 集成测试基础设施性能优化——async 测试转换、fixture scope 提升、批量 INSERT

### Modified Capabilities

（无 spec 级行为变更，仅测试基础设施实现调整）

## Impact

- 受影响文件：`test_vector_store_reindex.py`（async 转换）、`test_agent_admin_api.py` / `test_stats_admin_api.py` / `test_provider_admin_api.py`（fixture scope）、`test_memory_layer.py`（bulk INSERT）
- 不影响任何生产代码
- 不影响测试语义和覆盖范围，只改执行效率
- 无 API 变更，无依赖变更
