## ADDED Requirements

### Requirement: unified-migration-import
集成测试中所有使用 `apply_migrations` 的文件（`test_migrations.py` 本身除外）必须从 `tests.integration._migration_template` 导入，确保进程级 `lru_cache` 缓存生效。

#### Scenario: migration 仅执行一次
- **WHEN** 同一进程内多个测试调用 `apply_migrations`
- **THEN** Alembic `upgrade head` 只执行一次，后续调用通过 `shutil.copy` 复制模板

#### Scenario: 测试隔离保持不变
- **WHEN** 两个测试各自调用 `apply_migrations(tmp_path / "x.db")`
- **THEN** 每个测试得到独立的 SQLite 文件，互不干扰

---

### Requirement: no-sync-asyncio-run-in-tests
集成测试不得在同步测试函数（`def`）内使用 `asyncio.run()` 调用 async 函数；应改为 `async def` 测试函数。

#### Scenario: async 测试正常执行
- **WHEN** 测试函数为 `async def`，调用 `await upsert(...)` / `await search(...)`
- **THEN** 测试在单一 event loop 内完成，无额外 loop 创建/销毁开销

---

### Requirement: module-scoped-api-client-fixture
高频 API 测试文件（单文件测试数 ≥ 10 且以读/查询为主）的 `client` fixture scope 为 `module`；
需要写入且依赖干净状态的测试使用独立的 function-scoped 辅助 fixture。

#### Scenario: module scope 下多个读测试共享 client
- **WHEN** 同一模块内多个只读测试共用一个 `TestClient`
- **THEN** `FastAPI()` + `apply_migrations` 只初始化一次，测试结果不受影响

#### Scenario: 写测试保持隔离
- **WHEN** 写测试需要干净的数据库状态
- **THEN** 使用独立 function-scoped db/client，避免与其他测试共享状态

---

### Requirement: bulk-insert-in-test-setup
测试 setup 中批量写入多行数据时，使用单一连接 + `executemany`，而非循环单行 `sqlite3.connect` + `execute`。

#### Scenario: 批量插入 memory_items
- **WHEN** 测试需要预置 85 行 `memory_items`
- **THEN** 通过单次 `sqlite3.connect` + `conn.executemany(...)` 完成，连接数为 1
