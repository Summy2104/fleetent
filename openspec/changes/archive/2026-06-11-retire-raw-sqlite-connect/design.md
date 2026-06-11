## Context

复核 src 后发现仍有 4 处业务 store 裸 `sqlite3.connect`（排除 `db.py` 边界本体）：

- `runtime/layered_budget.py`（`budget_usage`）：`from fleetent.user_store import DB_PATH` + `sqlite3.connect(DB_PATH)` + `init_db()` 自建表。`budget_usage` 本就 per-agent（代码注释：cross-agent/global scope 已删、task scope 不持久化），但落全局 `DB_PATH`（管理库）。与 `agent-runtime-db-routing-cleanup` 收编的 4 张表同类，但当时**漏了它**；且不在统一 `MIGRATIONS` / data-model §3.3。
- `user_store.py`（`users`/`api_keys`）：`_conn() = sqlite3.connect(DB_PATH)`，SQL 用 `?` 占位（legacy 风格）。
- `platform/tenancy/store.py`（`tenants`/`teams`）：`_conn() = sqlite3.connect(DB_PATH)`，SQL 已用 named。
- `schema_migrations.py`：迁移引擎本体（设 `user_version`、跑 DDL），裸 connect 合理 → 豁免。

参照已迁移的 `schedule_store`：`db = create_database(Settings().database_url)`；`with db.transaction() as conn: conn.execute(DDL)`；`db.execute("… WHERE id = :id", {"id": …})`。`db.py` 自动加 WAL + busy_timeout。

## Goals / Non-Goals

**Goals:**
- `budget_usage` 归位 per-agent `agent_state.db`（`agent_scope` + `db.py` + 统一 `MIGRATIONS`），去裸 connect / 全局 `DB_PATH`。
- `user_store` / `tenancy.store` 经 `db.py` 边界（管理库），享 WAL + busy_timeout；`user_store` SQL 转 named。
- 移除作为 DB 入口的 `user_store.DB_PATH` re-export（确认无 importer 后）。

**Non-Goals:**
- `schema_migrations` 迁移引擎（豁免）。
- `budget_usage` 历史行迁移（period 自然滚动、ephemeral；旧管理库孤儿行部署方按需清理）。
- 改这些表的列 / 语义（原样）。
- 管理库 alembic schema 变更（`budget_usage` 离开管理库后，管理库不再需要它——若 alembic 曾定义则后续清理，本切片不强制）。

## Decisions

### D1：budget_usage 走 B 的同一套（agent_scope + 统一 MIGRATIONS）
完全照 `agent-runtime-db-routing-cleanup` 收编 `session_anti_flap`/`sub_agent_runs` 的方式：连接经 `agent_scope` 注入的 state DB 句柄，DDL append 进 `agent_state_migrations.py`（取当前 max+1）。**为何**：保持 agent 侧表"一物理文件一份统一 MIGRATIONS + 单 user_version"的一致模型；这是 B 该做漏做的补丁。

### D2：管理 store 只换连接边界，不挪库
`user_store` / `tenancy.store` 仍读写管理库（`Settings().database_url`），仅 `_conn()` 裸 connect → `create_database(...)`。**为何不一并挪/拆**：它们是管理侧、位置本就对；债只是"没走 db.py 边界"（缺 WAL/busy_timeout + 违反 boundary spec），换边界即可，挪库是另一回事。

### D3：user_store SQL 转 named parameters
迁移每条语句到 `db.execute` 时，`?` → `:name`（`database-runtime` 要求"迁移后 store 用 named"）。**为何顺手做**：反正每条语句都要碰；留 `?` 会违反既有 spec。

### D4：移除 DB_PATH re-export（确认无 importer）
本切片后 `layered_budget`/`tenancy` 不再 import `user_store.DB_PATH`（`context`/`sub_agent` 已由 B 去除）。grep 确认无其它 DB-入口 importer 后，移除该 re-export；测试改用 DB fixture / `Settings()` 注入。**为何**：boundary spec 禁止 `DB_PATH` re-export 作 DB 入口；留着是可被误用的旁路。

## Risks / Trade-offs

- [统一 MIGRATIONS 版本号竞争] → 取仓库当时实际 max+1，不硬编码。
- [user_store SQL 转 named 出错（漏改、命名错）] → 逐语句 TDD，覆盖 create/get/list/update/authenticate 等既有行为；`make test-pr` 对照基线。
- [DB_PATH re-export 仍有隐藏 importer / 测试 monkeypatch] → grep 全仓确认；逐个改测试隔离方式后再删 re-export。
- [budget_usage 历史行不迁移导致预算"清零"] → period 本就滚动重置、ephemeral，清零等价于新周期，无业务损失。
- [管理 store 经 db.py 后事务语义变化] → 用 `db.transaction()` 包写操作，与原 `with _conn()` 语义对齐；测试覆盖回滚。

## Migration Plan

1. `budget_usage` DDL append 进统一 `MIGRATIONS`；`layered_budget` 连接改 agent_scope + db.py、删裸 connect/DB_PATH import。
2. `user_store` `_conn` → `create_database`，SQL 转 named；`tenancy.store` `_conn` → `create_database`。
3. grep 确认无 DB-入口 importer 后移除 `user_store.DB_PATH` re-export；改测试隔离。
4. 验证基线：无 platform、管理库表不存在下 `fleetent agent run` 可完成，`budget_usage` 落 agent 自己的 `agent_state.db`。
5. 回滚：纯连接路径 + schema 归属变更，无数据迁移；回滚即还原连接与 MIGRATIONS。

## Open Questions

- 无（budget_usage 归属、管理 store 边界迁移、DB_PATH 去除均已定）。
