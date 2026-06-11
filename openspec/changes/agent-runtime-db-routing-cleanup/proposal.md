## Why

持久层 #3 把 agent 侧表迁入 per-agent `agent_state.db`（经 `agent_scope` 路由 + 嵌入式 Y + 统一 `MIGRATIONS`），但有 4 张 agent 运行时表没被收编（验证 data-model ER 图时发现）：

- `session_anti_flap`（`runtime/context.py`）、`sub_agent_runs`（`runtime/sub_agent_lifecycle.py`）：经 `from fleetent.user_store import DB_PATH` + **裸 `sqlite3.connect(DB_PATH)`** 落库，不走 `agent_scope`、不经 `db.py`。standalone `agent run` 下 boot 重定向 `DB_PATH` 到 agent home 尚能落对，但在 **platform 多 agent（#3 per-tenant 物理分区）** 下，`DB_PATH` = 共享管理库 → agent 运行时数据写进 platform 管理库，**违反「agent 数据严禁写 platform 表」铁律 + 跨 agent 共享（非物理隔离）+ 禁裸 `sqlite3.connect` + #3 路由**。
- `memory_maintenance_proposals`（`memory/proposal_store.py`）、`skill_proposals`（`reflection/reflection.py`）：经 store 注入路由到 `agent_state.db`（**库对**），但表由 legacy `ensure_schema` 建、**不在统一 `MIGRATIONS`**——违反 #3「一物理文件一份统一 `MIGRATIONS` + 单 `user_version`」；且 `reflection._database()` 在 `_state_db` 未注入时 fallback 到 `Settings().database_url`（管理库），是潜在错位路径。

收尾这 4 张，#3 的 agent 侧落库才完整、一致。

## What Changes

- **`session_anti_flap` / `sub_agent_runs` 改经 `agent_scope` + `db.py`**：去掉 `from user_store import DB_PATH` 与裸 `sqlite3.connect`，schema 经 per-agent `agent_state.db` 的统一 `MIGRATIONS`（Y）建立、读写经统一 DB 边界，使其在多 agent 下落入各自 `agent_state.db`、不再触管理库。
- **`memory_maintenance_proposals` / `skill_proposals` 折进统一 `MIGRATIONS`**：DDL 原样 lift 进 `runtime/agent_state_migrations.py`（append 在当前最大版本之后），不再由独立 `ensure_schema` 建；移除 `reflection._database()` 的管理库 fallback（无 `_state_db` 注入时不得落管理库）。
- **per-agent 表清单补全**：`agent-data-isolation` 的「boot 后 agent DB 含全部 agent 侧表」清单纳入这 4 张。

不在本切片：既有管理库中 `session_anti_flap` / `sub_agent_runs` 的**历史行**迁移（属 ephemeral 运行时数据，按 #3「上线前不迁移数据」新建即可，旧行作孤儿，由部署方按需清理）。

## Capabilities

### New Capabilities
<!-- 无；均为既有能力的需求扩展 -->

### Modified Capabilities
- `agent-db-schema-self-init`: 新增 `session_anti_flap` / `sub_agent_runs` 经 `agent_scope` + per-agent 嵌入式 Y 建 schema（去裸 `sqlite3.connect`、去全局 `DB_PATH`）；`memory_maintenance_proposals` / `skill_proposals` 纳入统一 `MIGRATIONS`、移除管理库 fallback。
- `agent-data-isolation`: boot 后 per-agent `agent_state.db` 的 agent 侧表清单补入这 4 张（确保多 agent 下各自隔离、不落共享管理库）。

## Impact

- **代码**：`runtime/agent_state_migrations.py`（统一 MIGRATIONS append 4 张表 DDL）、`runtime/context.py`（`session_anti_flap` 改经 `agent_scope`/`db.py`）、`runtime/sub_agent_lifecycle.py`（`sub_agent_runs` 同）、`memory/proposal_store.py`（经统一迁移、去独立 ensure_schema）、`reflection/reflection.py`（`skill_proposals` 入统一迁移、去管理库 fallback）。
- **owned tables**：`session_anti_flap` / `sub_agent_runs` 物理归属由「管理库/全局」改为 per-agent `agent_state.db`；`memory_maintenance_proposals` / `skill_proposals` schema 改由统一 `MIGRATIONS` 维护。
- **config namespace**：无；**cross-module**：`tenant_router.agent_scope`、`db.py`、`agent_state_migrations`。
- **migration/shim**：append 新版本到统一 `MIGRATIONS`；`CREATE TABLE IF NOT EXISTS` 对 legacy `ensure_schema` 已建表幂等无害；旧管理库中的同名孤儿表/行不动（文档注明）。
- **验证基线**：改后 agent 仍能在「无 platform、管理库表不存在」下完成 `fleetent agent run`，且这 4 张表落入 agent 自己的 `agent_state.db`。
