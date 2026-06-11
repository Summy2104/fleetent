# schema-residue-cleanup

## Why

持久层重设计（#1–#4）收尾后对照实测发现：管理库 Alembic head 仍会建出 4 张零业务归属的"幽灵表"（真相源已迁走或方案已被取代），`blocked_registrations` 由 store 运行时自建表、违反"管理表 Alembic-only"双权威契约，agent 侧 `sessions` 索引还带着与"归属由物理库圈定"哲学矛盾的 `agent_name` 遗留列。三者都是潜在的双真相源误导，且"上线前不迁移数据"的清理窗口即将关闭。

## What Changes

- **管理库 drop 4 张幽灵表**（Alembic 077，延续 073–076 清扫系列）：
  - `shared_memory_items` — 真相源已在 per-tenant `shared_memory.db`（嵌入式 Y），管理库副本零路由
  - `memory_maintenance_proposals` / `skill_proposals` — agent 侧已由 unify-self-evolution-model（Y v25/v26）统一进 `reflection_proposals`，管理库副本全仓零代码引用
  - `skill_hits`（迁移 057 引入）— 已被 `skill_hit` trace 事件 + platform 读投影方案取代（`builtin_tools._record_skill_hit` 写 trace，`skill_admin_store` 读 trace），表无人写也无人读
- **`blocked_registrations` 收编进 Alembic**（建表迁移，幂等承接 store 既建的同构表）；`governance/blocklist.py` 去 `CREATE TABLE IF NOT EXISTS` 自建（`_init_db`）、去 `DB_PATH` re-export、`?` 占位符改 named params。表是活的（`platform.user_management.block_service` 写、`user_store` 注册路径查），只改 schema 权威与代码风格，行为不变
- **agent 侧 `sessions` 索引 drop `agent_name` 列**（`agent_state_migrations.py` 追加 Y 新版本，`ALTER TABLE sessions DROP COLUMN`）：per-agent 物理库内该列恒为常量，且无任何下游消费（platform 读投影只 count；`list_by_user` 调用方不读该字段）；同步收敛 `session/index.py` 读写列与 `session/manager.py` 参数链。**管理库 `session_meta.agent_name` 不动**（platform 跨 agent 语义正当）
- **修复 3 处 canonical spec 预存漂移**（均在本 change 爆炸半径内）：`reflection` 仍要求 reflection-owned `skill_proposals` 表（Y 后应为 `reflection_proposals(domain=skill)`）；`agent-data-isolation` boot 场景仍引用已退役的 `agents/<name>/data/fleetent.db` 与已删提案表；`memory-layer` 共享记忆 schema 场景措辞明确"仅住 per-tenant 库、无管理库副本"
- **`docs/architecture/data-model.md` 修补**：§3.1/§3.3 图补 `scheduled_tasks`（含 `session_id`→`sessions`、`user_id`⇢`users` 两条边）；§3.1 `vector_items` 改为按 `mem:`/`shared:`/`kb:` 三家族 fan 到各自真相源；§3.2 补列 `agent_secrets`、`kb_connectors`、`session_meta`（注明与 agent 侧 `sessions` 索引的职责区分及跨库引用）；`blocked_registrations` 标注"已收编 Alembic"

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `user-blocklist`: `blocked_registrations` 的 schema 权威从 store 自建改为 Alembic-only；store 不再 `_init_db`、不再 re-export `DB_PATH`、SQL 用 named params
- `session-metadata-index`: 索引元数据集合移除 `agent_name`（per-agent 库归属由物理文件圈定）
- `reflection`: "Skill proposals are persisted" 场景由 `skill_proposals` 表修正为 `reflection_proposals(domain=skill)`（对齐 unify-self-evolution-model 既成事实）
- `agent-data-isolation`: agent boot 后表清单场景对齐现状（`agent_state.db` + 现行 11→12 张表口径，去掉 `fleetent.db` 与已删提案表）
- `memory-layer`: Shared memory schema 场景明确表仅由 per-tenant `shared_memory.db` 的嵌入式 Y 持有，管理库不再有同名副本
- `agent-db-schema-self-init`: "memory_maintenance_proposals / skill_proposals 纳入统一 MIGRATIONS" 要求对齐 Y 后现实（统一 `reflection_proposals`，历史两表已 DROP，管理库无副本）

## Impact

- **owning package**：`platform`（Alembic 迁移、blocklist 所依的管理库）、`governance`（blocklist.py）、`session`（index.py/manager.py）、`runtime`（agent_state_migrations.py）
- **public API surface**：`governance.blocklist.is_registration_blocked` / `ban_registration` 签名不变；`session/manager.py` 保存路径的 `agent_name` 参数移除（内部协作面，外部 run kwargs 中的 `agent_name` 仍用于 agent 配置解析，不受影响）
- **owned tables**：管理库 drop `shared_memory_items` / `memory_maintenance_proposals` / `skill_proposals` / `skill_hits`，新增 Alembic 接管 `blocked_registrations`；`agent_state.db` 的 `sessions` 表 drop `agent_name` 列（Y 新版本）
- **config namespace**：无
- **cross-module dependencies**：blocklist 仍经 `user_store._conn`（管理库连接路径，platform-managed 场景）；session index 经 `set_state_db` 注入，无新增依赖；不触碰 agent/platform 解耦边界（agent 运行时零 platform import 现状不变）
- **migration / shim plan**：无模块移动；Alembic 077（drop ×4）+ 078（create blocked_registrations，`IF NOT EXISTS` 语义承接存量自建表）；agent 侧 Y 追加一版（drop column，forward-only，无数据迁移——上线前窗口）
- **测试**：杜绝双真相源回归——管理库 schema 断言（4 表不存在、blocked_registrations 存在）落 integration；blocklist 行为测试改造为不依赖 store 自建；session index 列收敛的单测/集成测试同步
