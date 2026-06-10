## 1. approvals schema 迁 per-agent 库

- [x] 1.1 写失败测试：空 per-agent 库经 Y 迁移后含 `approvals`（+ allowlist）表，结构等价于现 approval_store ensure_schema
- [x] 1.2 实现：把 approvals + allowlist DDL 作为新版本步 **append 进统一列表 `runtime/agent_state_migrations.py`**（版本号接该列表**当前 max 之后**，勿硬编；**不另起独立列表**），跑绿 1.1

## 2. 连接走 agent_scope + 接线

- [x] 2.1 写失败测试：approval_store 连接来自 `agent_scope(...).state_db`；护栏断言无 `ensure_schema(db_path)`-into-global 残留
- [x] 2.2 实现：approval_store / allowlist 连接走 agent_scope（统一 db_path→agent_scope）；agent_app 审批接线，跑绿 2.1

## 3. 双权威清理（drop alembic 孤立定义）

- [x] 3.1 写失败测试：`alembic upgrade head` 后管理库**不含** `approvals` 表；先断言管理库无活 approvals 写入路径（确认可 drop）
- [x] 3.2 实现：新增 alembic 迁移 drop 管理库 `approvals` 定义，跑绿 3.1

## 4. 收尾

- [x] 4.1 不得 import platform、无新增裸 sqlite3.connect、named params；依赖护栏
- [x] 4.2 确认 per-agent 迁移链完成：全仓无 agent 侧 store 再 ensure_schema-into-global（REMOVE 的过渡要求成立）
- [x] 4.3 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate per-agent-approvals-lib --strict`
