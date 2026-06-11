## ADDED Requirements

### Requirement: 剩余 legacy 管理 store 迁入 db.py 边界
`user_store`（`users` / `api_keys`）与 `platform.tenancy.store`（`tenants` / `teams`）SHALL 经统一 `db.py` 边界（`create_database(Settings().database_url)` 取管理库句柄）执行 SQL，MUST NOT 再裸 `sqlite3.connect()`、MUST NOT 再以 `from user_store import DB_PATH` re-export 作为数据库入口；其 SQL SHALL 使用 named parameters。迁移引擎 `schema_migrations`（设 `PRAGMA user_version`、跑 DDL 的 schema 层本体）显式豁免本要求，可继续直接打开连接。

#### Scenario: 管理 store 经 db.py 连接
- **WHEN** `user_store` 或 `tenancy.store` 读写其表
- **THEN** 经 `db.py` 的 `SQLiteDatabase`（`execute` / `transaction`）完成，连接享 WAL + busy_timeout，不出现裸 `sqlite3.connect`

#### Scenario: 不再以 DB_PATH re-export 作 DB 入口
- **WHEN** 审视 `user_store` 与 `platform/tenancy/store.py`
- **THEN** 不存在作为数据库入口的 `DB_PATH` 裸连接路径；测试经 DB fixture / `Settings().database_url` 隔离，而非 monkeypatch `DB_PATH`

#### Scenario: 迁移引擎豁免
- **WHEN** `schema_migrations` 运行迁移
- **THEN** 允许其直接打开连接（设 `user_version`、执行 DDL），不受本要求约束
