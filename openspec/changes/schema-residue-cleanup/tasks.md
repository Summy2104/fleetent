# schema-residue-cleanup Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. 管理库幽灵表 drop（Alembic 077）

- [ ] 1.1 [测试] integration：新增/扩展管理库 schema 对账测试——alembic 升到 head 后断言 `shared_memory_items`、`memory_maintenance_proposals`、`skill_proposals`、`skill_hits` 四表**不存在**（先红：当前 head 仍建出它们）
- [ ] 1.2 [实现] 新增 `migrations/versions/077_drop_residual_tables.py`：`drop_table` ×4（含 057 的 `ix_skill_hits_skill_name` 索引随表消失）；downgrade 按原 DDL 重建空表（057 / 068 来源）→ 1.1 转绿

## 2. blocked_registrations 收编（Alembic 078 + blocklist 改造）

- [ ] 2.1 [测试] integration：head 后断言 `blocked_registrations` 表存在且含 email/reason/batch_id/created_at 列；并覆盖"幂等承接"——先用旧 store DDL 自建表并插入一行封禁，再跑迁移，断言成功且行保留（先红：当前 Alembic 不建此表）
- [ ] 2.2 [测试] unit/integration：改造 blocklist 行为测试为不依赖 store 自建表（经统一 DB fixture 建 schema），断言 `ban_registration` / `is_registration_blocked` 行为不变；断言 `governance/blocklist.py` 源码无 `CREATE TABLE`、无 `DB_PATH` re-export（守护测试，先红）
- [ ] 2.3 [实现] 新增 `migrations/versions/078_onboard_blocked_registrations.py`：`inspector.has_table` 短路 + 建表（列定义抄 blocklist.py 现 DDL）→ 2.1 转绿
- [ ] 2.4 [实现] `governance/blocklist.py`：删 `_init_db` 与所有调用点、删 `DB_PATH` re-export、`?` 占位符改 named params；受影响测试改用 fixture → 2.2 转绿

## 3. agent 侧 sessions.agent_name 移除（嵌入式 Y）

- [ ] 3.1 [测试] integration：打开最新 Y 版本的 `agent_state.db`，断言 `sessions` 表无 `agent_name` 列；并覆盖升级路径——以旧版本（含 agent_name、有存量行）库 migrate-on-open 后列消失、其余元数据保留（先红）
- [ ] 3.2 [测试] 调整 `session/index.py` / `session/manager.py` 相关单测与集成测试：upsert/查询不再含 `agent_name`（先红）
- [ ] 3.3 [实现] `runtime/agent_state_migrations.py` 追加新版本：`ALTER TABLE sessions DROP COLUMN agent_name` → 3.1 转绿
- [ ] 3.4 [实现] `session/index.py`（upsert 列、`_SELECT_COLS`、行映射）与 `session/manager.py`（保存路径参数链）去 `agent_name`；全仓 grep `agent_name` 复核无索引列残留引用（run-kwargs / agent-config / 管理库 `session_meta` 的用途不动）→ 3.2 转绿

## 4. 文档同步

- [ ] 4.1 `docs/architecture/data-model.md`：§3.1 宏观图 AGENT 框补 `scheduled_tasks`；`vector_items` 改三家族 fan 边（`mem:`→`memory_items`、`shared:`→`shared_memory_items`、`kb:`→`knowledge_chunks`）；§3.3 明细图补 `scheduled_tasks`（`session_id`→`sessions`、`user_id`⇢管理库 `users`）；sessions 实体描述去 `agent_name`
- [ ] 4.2 `docs/architecture/data-model.md` §3.2：补列 `agent_secrets`、`kb_connectors`、`session_meta`（注明 admin takeover/pinned 治理元数据职责、与 agent 侧 `sessions` 索引的区分、`session_id` 跨库引用）；`blocked_registrations` 标注"Alembic 收编（078）"；删去已 drop 四表的任何残留提法
- [ ] 4.3 复核 `docs/capabilities/`（memory.md / reflection.md / skill.md / session.md）无对四张幽灵表与 `sessions.agent_name` 的残留描述，有则同步

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 5.2 `openspec validate schema-residue-cleanup` 通过；所有 checkbox 标记 `[x]`
