## Context

集成测试套件约 186 个文件，静态分析发现三类仍需修复的基础设施开销（原始分析提到四类，「migration 导入路径分裂」经核查为误报——`test_migrations.py` 已 re-export 自 `_migration_template`，`lru_cache` 缓存已生效）：

1. **同步函数内反复 `asyncio.run()`**：`test_vector_store_reindex.py` 两个测试均为 `def`（非 `async def`），内部 10 次 `asyncio.run()`，每次创建并销毁 event loop（10–30ms/次）。项目已配置 `asyncio_mode = auto`，直接改 `async def` 即可。

2. **API fixture 每 test 全量重建**：高频 API 测试文件的 `client` fixture 默认 `scope="function"`，每 test 构造 `FastAPI()` + `include_router` + `TestClient` + `apply_migrations`（shutil.copy）。同一文件 20–30 个 test 重复 20–30 次，累积 200–500ms。

3. **循环单行 INSERT**：`test_memory_layer.py` 用循环调用 `_insert_memory_row`，每次独立 `sqlite3.connect` + 单行 INSERT，85 次调用 ≈ 85 个连接。改为 `executemany` 单连接批量写入。

## Goals / Non-Goals

**Goals:**
- `test_vector_store_reindex.py` 两个测试改为 `async def`，消除 `asyncio.run()`
- 高频 API 测试文件 `client` fixture 提升 `scope="module"`
- `test_memory_layer.py` 批量 INSERT 替代循环单行写

**Non-Goals:**
- 不改变任何测试覆盖范围或断言语义
- 不重构测试目录结构
- 不引入 pytest-xdist 并行运行（单独变更决策）
- 不批量迁移所有 `monkeypatch` 到更高 scope（影响过广，风险与收益不对称）

## Decisions

**D1: `client` fixture 提升 scope 时，`monkeypatch` → `pytest.MonkeyPatch()` 手动管理**

`monkeypatch` fixture 是 `scope="function"`，无法注入 module-scoped fixture。改为：
```python
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("db")
    # ... setup with mp.setenv / mp.setattr ...
    yield test_client
    mp.undo()
```
写操作测试（需要干净状态）用独立 function-scoped `db_path` fixture，不共享 module client。

**D2: `asyncio.run()` → `async def`，无需额外 mark**

`pytest.ini` 已设 `asyncio_mode = auto`，async 测试函数无需 `@pytest.mark.asyncio`。`reindex()` 是同步函数，保持直接调用；只有 `upsert`/`search`/`ingest_text` 需要 `await`。

**D3: `executemany` 复用同一连接**

`test_memory_layer.py` 中新增 `_insert_memory_rows` 批量版本，接受 list of tuples；循环测试改用此版本。保留单行版 `_insert_memory_row` 供需要逐行控制参数的场景使用。

## Risks / Trade-offs

- **Module scope DB 共享**：写操作测试漏改会产生隐性顺序依赖；通过 `make test-pr` 无新增失败来验证
- **`asyncio.run()` 转换**：`reindex()` 是同步函数，不需要 await，转换后需确认只有 `upsert`/`search`/`ingest_text` 被 await
- **scope="module" 的 `tmp_path_factory` 路径**：每次 `mktemp` 返回新目录，module fixture 只调用一次，测试间共享同一 tmp dir，符合预期
