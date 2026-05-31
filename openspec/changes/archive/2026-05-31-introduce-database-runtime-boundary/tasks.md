## 0. 前置确认

- [x] 0.1 确认本 change 不引入 ORM、不引入 PostgreSQL driver、只实现 SQLite adapter
- [x] 0.2 确认参考迁移 store 为 `schedule_store`，不迁移 `user_store`

## 1. database_url 配置

- [x] 1.1 Write failing tests: `Settings.database_url` 未配置时默认指向 `sqlite:///data/users.db`
- [x] 1.2 在 `config.py` 新增 `database_url` 配置，保持现有配置加载方式不变
- [x] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. DB runtime 核心接口

- [x] 2.1 Write failing tests: runtime 可从 SQLite database_url 创建 database，非 SQLite scheme 初始化失败且错误信息明确
- [x] 2.2 新建 `src/fleetent/db.py`：定义 `Database` / `DbConnection` / `DbResult` 协议或类，以及 SQLite adapter 工厂
- [x] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. named parameters 与结果读取

- [x] 3.1 Write failing tests: `db.execute` 支持 named parameters；SELECT 可 `fetchone` / `fetchall`；UPDATE/DELETE 可读取 `rowcount`
- [x] 3.2 实现 SQLite adapter 的 execute/result 包装，禁止 store 直接接触裸 cursor
- [x] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. 事务边界

- [x] 4.1 Write failing tests: transaction 正常退出提交，异常退出回滚
- [x] 4.2 实现 database runtime 的 transaction 上下文
- [x] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. 迁移 schedule_store 作为参考实现

- [x] 5.1 Write failing tests: `schedule_store` 测试不再 monkeypatch `schedule_store.DB_PATH`，改用 database_url/runtime 隔离；create/list/delete 行为保持不变
- [x] 5.2 修改 `schedule_store` 通过 database runtime 访问数据库，SQL 改为 named parameters，移除该 store 的直接 `sqlite3.connect` 与 `DB_PATH` 入口
- [x] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. schema lifecycle 边界

- [x] 6.1 Write failing tests/static check: 新增 runtime 与迁移后的 `schedule_store` 不包含 `CREATE TABLE IF NOT EXISTS` 或 `PRAGMA table_info`
- [x] 6.2 确认 `schedule_store` 所需表由既有 Alembic migration 覆盖；如缺失，新增 Alembic migration 而不是 store-local `_init_db()`
- [x] 6.3 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. 收尾验证

- [x] 7.1 运行 `uv run pytest -x -q`
- [x] 7.2 运行 `uv run ruff format src tests`
- [x] 7.3 运行 `uv run ruff check src tests`；全量检查因既有 lint 基线问题失败，本 change 相关文件的 ruff check 已通过
- [x] 7.4 运行 `uv run mypy src`；全量检查因既有 mypy 基线问题失败，本 change 相关源文件 mypy 已通过
- [x] 7.5 检查 `schedule_store` 不含 `sqlite3.connect`，且 `schedule_store` / `db.py` 不含 `DB_PATH` 或 `?` 占位符，确认 legacy 模式未扩散到 store 层

## 验证记录

- `uv run pytest -x -q`：通过，`363 passed`
- `uv run ruff format src tests`：已运行；为避免无关格式化 churn，仅保留本 change 相关文件格式化结果
- `uv run ruff check src tests`：已运行；失败来自既有 lint 基线问题（如 `agent_loop.py`、`cron_scheduler.py`、多组旧测试），未在本 change 修复
- 本 change 相关文件 ruff check：通过
- `uv run mypy src`：已运行；失败来自既有 mypy 基线问题
- `uv run mypy src/fleetent/db.py src/fleetent/schedule_store.py src/fleetent/config.py`：通过
