## 0. 前置确认

- [ ] 0.1 确认本 change 不引入 ORM、不引入 PostgreSQL driver、只实现 SQLite adapter
- [ ] 0.2 确认参考迁移 store 为 `schedule_store`，不迁移 `user_store`

## 1. database_url 配置

- [ ] 1.1 Write failing tests: `Settings.database_url` 未配置时默认指向 `sqlite:///data/users.db`
- [ ] 1.2 在 `config.py` 新增 `database_url` 配置，保持现有配置加载方式不变
- [ ] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. DB runtime 核心接口

- [ ] 2.1 Write failing tests: runtime 可从 SQLite database_url 创建 database，非 SQLite scheme 初始化失败且错误信息明确
- [ ] 2.2 新建 `src/fleetent/db.py`：定义 `Database` / `DbConnection` / `DbResult` 协议或类，以及 SQLite adapter 工厂
- [ ] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. named parameters 与结果读取

- [ ] 3.1 Write failing tests: `db.execute` 支持 named parameters；SELECT 可 `fetchone` / `fetchall`；UPDATE/DELETE 可读取 `rowcount`
- [ ] 3.2 实现 SQLite adapter 的 execute/result 包装，禁止 store 直接接触裸 cursor
- [ ] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. 事务边界

- [ ] 4.1 Write failing tests: transaction 正常退出提交，异常退出回滚
- [ ] 4.2 实现 database runtime 的 transaction 上下文
- [ ] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. 迁移 schedule_store 作为参考实现

- [ ] 5.1 Write failing tests: `schedule_store` 测试不再 monkeypatch `schedule_store.DB_PATH`，改用 database_url/runtime 隔离；create/list/delete 行为保持不变
- [ ] 5.2 修改 `schedule_store` 通过 database runtime 访问数据库，SQL 改为 named parameters，移除该 store 的直接 `sqlite3.connect` 与 `DB_PATH` 入口
- [ ] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. schema lifecycle 边界

- [ ] 6.1 Write failing tests/static check: 新增 runtime 与迁移后的 `schedule_store` 不包含 `CREATE TABLE IF NOT EXISTS` 或 `PRAGMA table_info`
- [ ] 6.2 确认 `schedule_store` 所需表由既有 Alembic migration 覆盖；如缺失，新增 Alembic migration 而不是 store-local `_init_db()`
- [ ] 6.3 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. 收尾验证

- [ ] 7.1 运行 `uv run pytest -x -q`
- [ ] 7.2 运行 `uv run ruff format src tests`
- [ ] 7.3 运行 `uv run ruff check src tests`
- [ ] 7.4 运行 `uv run mypy src`
- [ ] 7.5 检查 `rg "sqlite3.connect|DB_PATH|\\?" src/fleetent/schedule_store.py src/fleetent/db.py`，确认迁移后的代码未扩散 legacy 模式
