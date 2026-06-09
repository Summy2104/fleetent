## 1. env.py 从 app 配置取迁移 URL

- [x] 1.1 Write failing test (`tests/integration/test_alembic_env_url.py`)：设 `DATABASE_URL=sqlite:///<tmp>` 编程式运行 `alembic upgrade head`，断言表建在该 tmp 库；未设 `DATABASE_URL` 时回退 `alembic.ini` 默认。先见红（当前 env.py 忽略 `DATABASE_URL`）。
- [x] 1.2 Implement：`migrations/env.py` 的 `run_migrations_online` 在 `engine_from_config` 前，用 `fleetent.config.Settings().database_url` 覆盖 `config` 的 `sqlalchemy.url`（env 未设则保留 ini 默认）。见绿。

## 2. Schema 漂移护栏

- [x] 2.1 Write failing test (`tests/integration/test_schema_drift_guard.py`)：空 tmp 库 A 跑 `alembic upgrade head`；空 tmp 库 B 调用全部 `ensure_schema()`（traces / memory.store / reflection / kb.operations / session.index）；对 B 中每张表断言其列集合 == A 同名表。**teeth**：临时扰动一个 `ensure_schema` 列定义，断言护栏转红；恢复后转绿。
- [x] 2.2 Implement：若存在真实漂移，对齐 `ensure_schema` DDL 与 alembic head 使测试转绿；若已一致，护栏即锁定现状（teeth 已由扰动验证）。

## 3. 消灭 users.db：session 元数据并入统一库

- [x] 3.1 Write failing test (`tests/integration/test_session_index_unified_store.py`)：`session.index` 写入由 `DATABASE_URL` 指向的统一库（非硬编码 `users.db`）；暴露幂等 `ensure_schema(db)`；模块内不出现 `sqlite3.connect` 与 `users.db`。先见红。
- [x] 3.2 Implement：重写 `session/index.py` 用 `fleetent.db.create_database` + named params（`:session_id` 等）+ `ensure_schema(db)`；删除 `DB_PATH = users.db` 与裸 `sqlite3`；将 `session.index.ensure_schema` 接入 `runtime/agent_app._init_agent_db_schema`。见绿。

## 4. 文档对齐（无红绿）

- [x] 4.1 修正过时 docstring：`runtime/context.py`、`runtime/layered_budget.py`、`runtime/sub_agent_lifecycle.py` 中「users.db」表述改为实际存储位置（统一 `fleetent.db` / per-agent 库）。
- [x] 4.2 修正 `CLAUDE.md` 数据目录段：users.db 不再列为主库；补一句双 schema 权威（管理库 alembic / per-agent 库 ensure_schema）。
- [x] 4.3 修正 `docs/architecture/data-model.md`：删除已被推翻的「迁移链不可重放」结论，补「迁移链健康 + 双权威 + 三层拓扑终态」。（跳过：data-model.md 已在上个 session 改完）

## 5. 收尾验证

- [x] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 基线无新增失败；`openspec validate persistence-hygiene` 通过。
