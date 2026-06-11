## Context

#3 把 agent 侧表迁入 per-agent `agent_state.db`（`agent_scope` 路由 + 嵌入式 Y + 统一 `MIGRATIONS`），但 4 张 agent 运行时表漏收编（验证 data-model §3 ER 图时发现，已在该文档标 ⚠️）：

- `session_anti_flap`（`runtime/context.py:732-734`）、`sub_agent_runs`（`runtime/sub_agent_lifecycle.py:80-82`）：`from fleetent.user_store import DB_PATH` + 裸 `sqlite3.connect(DB_PATH)`，各自 `init_*_db()` 建表。standalone `agent run` 下 `agent_app.boot()` 重定向 `DB_PATH` 到 agent home，尚能落对；但 platform 多 agent（#3 per-tenant）下 `DB_PATH` = 共享管理库 → 运行时数据落 platform 管理库、跨 agent 共享。
- `memory_maintenance_proposals`（`memory/proposal_store.py`，经 `store.database()` = agent_scope 注入的 `_state_db`）、`skill_proposals`（`reflection/reflection.py`，经 `_database()`）：库对（agent_state.db）但表不在统一 `MIGRATIONS`，靠 legacy `ensure_schema`；`reflection._database()` 未注入 `_state_db` 时 fallback `Settings().database_url`（管理库）。

统一 `MIGRATIONS` 当前 6 表（v1..v13）：sessions/traces/reflection_reports/memory_items/approvals/approval_allowlist。

## Goals / Non-Goals

**Goals:**
- 4 张表都经 per-agent `agent_state.db`（`agent_scope` + `db.py`）落库，schema 由统一 `MIGRATIONS` 建。
- 去 `context.py` / `sub_agent_lifecycle.py` 的裸 `sqlite3.connect(DB_PATH)`。
- 去 `reflection._database()` 的管理库 fallback。

**Non-Goals:**
- 迁移管理库中既有 `session_anti_flap` / `sub_agent_runs` 历史行（ephemeral 运行时数据，新建即可，旧行作孤儿）。
- 改这 4 张表的 schema / 列（原样 lift）。
- standalone 单 agent 的 `fleetent.db` vs 多 agent `agent_state.db` 命名统一（既有张力，不在本切片）。

## Decisions

### D1：DDL 原样 lift 进统一 MIGRATIONS（append 在当前最大版本之后）
把 4 张表的 `CREATE TABLE`（+ 现有索引）按当前 `MIGRATIONS` 末尾版本号**递增 append**（不硬编码版本，取现 max+1 起）。**为何不各自留 ensure_schema**：#3 要求一物理文件一份统一 `MIGRATIONS` + 单 `user_version`；独立 ensure_schema 与 Y 引擎的 user_version 模型冲突、且漂移无护栏。`CREATE TABLE IF NOT EXISTS` 对 legacy 已建表幂等无害。

### D2：连接改经 agent_scope + db.py，删裸 sqlite3.connect
`context.py` / `sub_agent_lifecycle.py` 的 `_conn()` 从 `sqlite3.connect(DB_PATH)` 改为经 per-agent state DB 句柄（与 memory/traces 同源的注入/`agent_scope` 路径）。**为何**：裸连 + 全局 `DB_PATH` 是多 agent 落错库 + 绕 `db.py`（无 WAL/busy_timeout）的根因。

### D3：去 reflection 管理库 fallback
`reflection._database()` 删 `else: create_database(Settings().database_url)` 分支——无 `_state_db` 注入时按基线行为（拒/空），不得落管理库。**为何**：fallback 是 skill_proposals 落管理库的潜在路径，与隔离铁律冲突。

### D4：历史行不迁移
管理库里既有 `session_anti_flap` / `sub_agent_runs` 行不搬（防抖计数、子 agent 运行日志均 ephemeral）。**为何**：符合 #3「上线前不迁移数据、新 schema 全新建」；搬迁成本/风险 > 价值。文档注明旧行作孤儿、部署方按需清理。

## Risks / Trade-offs

- [统一 MIGRATIONS 版本号竞争（与其它在途 change append 撞号）] → 取当前 max+1 起、不硬编码；apply 时以仓库当时实际 max 为准。
- [legacy ensure_schema 与统一迁移 DDL 不一致] → lift 时逐列对齐原 DDL；`CREATE TABLE IF NOT EXISTS` + 测试断言列集一致。
- [context.py / sub_agent_lifecycle.py 改连接牵动其调用与测试 monkeypatch] → 这俩本就 re-export `DB_PATH` 供 monkeypatch；改为 state-db 注入后，测试改注入 per-agent 句柄（与 memory/traces 测试同模式）。
- [standalone 单 agent 行为回归] → 单 agent 下经 agent_scope 仍解析到该 agent 的库；加测试覆盖单 agent + 双 agent 隔离。

## Migration Plan

1. 统一 `MIGRATIONS` append 4 张表 DDL（max+1 起）。
2. `context.py` / `sub_agent_lifecycle.py` 改 agent_scope + db.py、删裸连。
3. `proposal_store` / `reflection` 去独立 ensure_schema / 管理库 fallback。
4. 验证基线：无 platform、管理库表不存在下 `fleetent agent run` 可完成，4 表落 agent 自己的 `agent_state.db`。
5. 回滚：纯 schema 归属 + 连接路径变更；回滚即还原连接与 MIGRATIONS（已写入 agent_state.db 的表无害保留）。

## Open Questions

- 无（4 张表的归属、迁移方式、fallback 处理均已定）。
