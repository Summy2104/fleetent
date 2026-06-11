## 1. budget_usage 归位 per-agent agent_state.db

- [x] 1.1 写测试（integration）：以统一 `MIGRATIONS` 打开全新 `agent_state.db` 后含 `budget_usage`，列集与原 `init_db` DDL 一致 —— 见红
- [x] 1.2 把 `budget_usage` 的 `CREATE TABLE` 原样 lift 进 `runtime/agent_state_migrations.py`，版本号取当前 max+1 起 append（不硬编码、不改列） —— 见绿
- [x] 1.3 写测试（integration）：platform 下两个 agent 各自累计预算，分别落各自 `agent_state.db`、互不可见、均不落管理库 —— 见红
- [x] 1.4 `runtime/layered_budget.py`：`_conn` 改经 `agent_scope` + `db.py`（删 `from user_store import DB_PATH` + 裸 `sqlite3.connect`），建表交统一 MIGRATIONS；读写改 `db.execute`/`transaction` —— 见绿
- [x] 1.5 grep 自查：`runtime/layered_budget.py` 无 `sqlite3.connect` / `user_store import DB_PATH`

## 2. user_store 迁入 db.py 边界 + named SQL

- [x] 2.1 写测试（integration）：`user_store` 经 db.py 后 create/get_by_id/get_by_email/list/update/authenticate 行为不变；连接享 WAL（`journal_mode=wal`） —— 见红
- [x] 2.2 `user_store.py`：`_conn()` → `create_database(Settings().database_url)`；各语句迁 `db.execute`/`db.transaction`，`?` 占位转 named parameters —— 见绿

## 3. tenancy.store 迁入 db.py 边界

- [x] 3.1 写测试（integration）：`platform/tenancy/store` 经 db.py 后 tenants/teams 的 create/list/update 行为不变，连接享 WAL —— 见红
- [x] 3.2 `platform/tenancy/store.py`：`_conn()` → `create_database(Settings().database_url)`，写操作走 `db.transaction()` —— 见绿

## 4. 移除 DB_PATH re-export + 收尾

- [x] 4.1 grep 全仓确认无「作为 DB 入口」的 `user_store.DB_PATH` importer（`context`/`sub_agent` 已由前序 change 去除；本 change 去除 `layered_budget`/`tenancy`）
- [x] 4.2 移除 `user_store` 的 `DB_PATH` re-export 作为 DB 入口的用法；受影响测试改用 DB fixture / `Settings()` 注入隔离，不再 monkeypatch `DB_PATH`
- [x] 4.3 grep 自查：业务层无裸 `sqlite3.connect`（仅剩 `db.py` 边界与 `schema_migrations` 引擎）
- [x] 4.4 同步 `docs/architecture/data-model.md` §3.3：`budget_usage` 列入 per-agent（10 表 → 11 表）并补进 §3.3 明细图
- [x] 4.5 验证基线：无 platform、管理库表不存在下 `fleetent agent run` 可完成，`budget_usage` 落 agent 自己的 `agent_state.db`
- [ ] 4.6 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
