## Why

持久层处于「向统一边界迁移的半途」，留下多处不一致（2026-06-09 排查确认）：

- **`migrations/env.py` 忽略 `DATABASE_URL`**：online 迁移只用 `alembic.ini` 硬编码的
  `sqlalchemy.url = sqlite:///data/fleetent.db`，与 app 的 `config.DATABASE_URL` 脱节。设
  `DATABASE_URL` 不影响迁移目标 → migrate 与运行可指向不同库（本次排查即因此误把真实库从 046 推到 048）。
- **双 schema 权威可漂移且无护栏**：管理库由 alembic 建表；per-agent 库由各 store 的
  `ensure_schema()`（`CREATE TABLE IF NOT EXISTS`）建表。二者对 agent-side 共享表
  （`traces`/`memory_items`/`reflection_reports`/KB）各写一份 DDL，靠手工保持一致、无自动校验 → 迟早分叉。
  且 `db-migration` 的「No raw schema creation」与 `agent-db-schema-self-init` 的 ensure_schema
  在表述上相互冲突，适用边界从未厘清。
- **`users.db` 残留**：`session/index.py` 用裸 `sqlite3.connect(data_dir/"users.db")` 建 `sessions`
  表，绕过统一 `db.py` runtime，违反 `db-migration`「No raw schema creation」。会话元数据 split-brain
  （`sessions` 在 users.db、`session_meta` 在 fleetent.db）。
- **过时文档**：`runtime/context.py`/`layered_budget.py`/`sub_agent_lifecycle.py` docstring 仍称数据存于
  `users.db`（实际在 fleetent.db）；`CLAUDE.md` 数据目录段把 users.db 列为主库；
  `docs/architecture/data-model.md` 残留一条已被推翻的「迁移链不可重放」结论。

本 change 是持久层归一化的**第一期（卫生 + 漂移护栏）**，为后续「管理库 schema 收编」「三层库分离」
「Identity 端口」打地基。

## What Changes

- `migrations/env.py` online 模式从 `config.DATABASE_URL`（`Settings().database_url`）取迁移 URL；
  `alembic.ini` 的 `sqlalchemy.url` 降为未设 env 时的回退。
- 新增 **schema 漂移护栏测试**：对每个 `ensure_schema()` 创建的表，断言其列集合与
  `alembic upgrade head`（空库）产出的同名表一致；锁住双权威不分叉。明确边界：**管理表 = 仅 alembic**；
  **agent-side 表 = ensure_schema + 与 alembic 保持一致**。
- `session/index.py` 改用统一 `db.py`（`create_database(DATABASE_URL)`）+ `ensure_schema()` 存 `sessions`
  元数据；删除裸 `sqlite3.connect` 与 `users.db` 路径；接入 `_init_agent_db_schema`。消灭 `users.db`。
- 修正过时 docstring + `CLAUDE.md` 数据目录段 + `docs/architecture/data-model.md`。

### Out of scope（后续 change，避免本期过大）

- **管理表收编进 alembic**（users/api_keys/quotas/invites/im_channel_allowlist/audit_log，现由 `_init_db`
  运行时建）—— 第二期。
- **三层库物理分离**（管理 / per-agent / 共享资源）+ KB/vector/共享记忆迁入共享库 —— 第三期。
- **`vector_store.db` → `fleetent_vector.db` 改名** —— 归第三期：现有 `vector-store` spec 规定「未配置
  时回退全局 `Settings.database_url`」，改名与「向量是否默认独立成文件」语义耦合，应与共享资源库一并决定。
- **Identity 端口**（根除 #1 泄漏）—— 第四期。

## Impact

- `migrations/env.py` — online 模式从 `config.DATABASE_URL` 注入迁移 URL
- `src/fleetent/session/index.py` — 改用 `db.py` + `ensure_schema`，删除 `users.db` 路径与裸 sqlite3
- `src/fleetent/runtime/agent_app.py` — `_init_agent_db_schema` 增加 `session.index.ensure_schema`
- `tests/integration/test_alembic_env_url.py` — 新增：迁移 URL 来自 `DATABASE_URL`
- `tests/integration/test_schema_drift_guard.py` — 新增：alembic-head vs ensure_schema 列一致
- `tests/integration/test_session_index_unified_store.py` — 新增：session 元数据走统一库
- docstrings：`runtime/context.py`、`runtime/layered_budget.py`、`runtime/sub_agent_lifecycle.py`
- docs：`CLAUDE.md`（数据目录段）、`docs/architecture/data-model.md`
