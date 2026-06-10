# approvals-schema-drift-hotfix

## Why

存量部署（如 v0.2.0 本地 daemon）的 `approvals` 表是旧形态（含 `approver_user_id`、无 `approver_actor`），而当前 `governance/approval_store.py` 的 UPDATE 语句引用 `approver_actor`。`ensure_schema()` 只做 `CREATE TABLE IF NOT EXISTS`，对存量表不补列，于是审批 resolve 落库抛 `sqlite3.OperationalError: no such column: approver_actor`——**所有 medium 风险工具（含 `run_code`）的审批门弹出后永远无法完成，工具永不执行**。2026-06-10 已在真实 Slack e2e 中复现并用手动 `ALTER TABLE` 临时止血，需要代码级修复让所有存量部署自愈。

## What Changes

- `governance/approval_store.py` 的 `ensure_schema()`：在 `CREATE TABLE IF NOT EXISTS` 之后探测 `approver_actor` 列，缺失则 `ALTER TABLE approvals ADD COLUMN approver_actor TEXT` 补列（幂等自愈）。
- 仅在「本次确实补了列」的分支内，从旧列回填历史数据：`UPDATE approvals SET approver_actor = approver_user_id WHERE approver_actor IS NULL`（补列发生 ⇒ 旧形态表 ⇒ `approver_user_id` 必然存在，回填不会引用不存在的列）。
- 不引入新的迁移机制、不戳 `PRAGMA user_version`、不改 alembic。

**定位声明（与 pending change `per-agent-approvals-lib`（持久层 3b-4）的关系）**：本切片是**止血 hotfix**，寿命到 3b-4 落地为止。3b-4 将把 approvals 整体迁入 per-agent `agent_state.db` 的统一嵌入式迁移列表（`runtime/agent_state_migrations.py`，one-file-one-user_version 原则），并 drop alembic 孤立定义；届时 `ensure_schema()`（连同本切片的补列逻辑）整体被替换。**本切片刻意不把 approvals 迁入嵌入式迁移引擎**：在全局 `fleetent.db` 上另立独立 MIGRATIONS + `user_version` 戳会与 one-file-one-stamp 原则冲突，且该机制在 3b-4 落地时即被拆除——为一张即将迁走的表建临时基础设施是过度设计。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `standalone-agent-approval`: 新增 requirement——存量 `approvals` 表缺 `approver_actor` 列时，`ensure_schema()` SHALL 自愈补列并回填旧列数据；审批 resolve 在旧形态存量库上不再崩溃。

## Impact

- **代码**：仅 `src/fleetent/governance/approval_store.py`（`ensure_schema` 一个函数）。
- **数据/schema**：存量 `approvals` 表新增可空列 `approver_actor`（非破坏、幂等）；旧列 `approver_user_id` 保留不动（3b-4 处置）。新建库不受影响（DDL 已含该列，探测分支为 no-op）。
- **测试**：integration 层覆盖三种存量形态——旧形态（仅 `approver_user_id`）自愈 + 回填；新形态（已有 `approver_actor`）no-op；重复调用幂等。
- **依赖/约束**：不 import platform；named parameters；不触碰 `db.py` 边界之外的连接。与 3b-4 无实现冲突（3b-4 整体替换 `ensure_schema` 时连本补丁一起替换）。
- **漂移护栏盲区说明**：approvals 不在 `agent-db-schema-self-init` 漂移护栏的校验清单（traces/memory/reflection）内，alembic 侧（`approver_user_id`）与 agent 侧（`approver_actor`）的分叉因此未被捕获——制度性修复（唯一真相源 + drop alembic 定义）属 3b-4 范围，本切片不展开。
