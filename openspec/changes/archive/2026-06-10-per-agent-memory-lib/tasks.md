## 1. memory schema 迁 per-agent 库（去 namespace 列）

- [x] 1.1 写失败测试：空 per-agent 库经 Y 迁移后含 `memory_items` 表、**不含 `namespace` 列**，其余结构等价于现 `memory/store.py` ensure_schema
- [x] 1.2 实现：把 `memory_items` DDL（去 namespace 列）作为新版本步 **append 进统一列表 `runtime/agent_state_migrations.py`**（版本号接该列表**当前 max 之后**，勿硬编 v4；**不另起独立列表**），跑绿 1.1

## 2. 连接走 agent_scope + 接线

- [x] 2.1 写失败测试：memory store 连接来自 `agent_scope(...).state_db`；护栏断言无 `create_database`/`ensure_schema`-into-global 残留
- [x] 2.2 实现：memory/store.py 连接走 agent_scope；删自连接；`agent_app._init_agent_db_schema` 接线，跑绿 2.1

## 3. 去 namespace 第二参（R2-叉2）

- [x] 3.1 写失败测试：`memory_namespace(user_id)` 单参返回 `mem:{user_id}`；memory `search`/`extract_and_update` 签名无 `namespace` 参
- [x] 3.2 实现：删 `memory_namespace` 第二参 + memory 操作的 `namespace` 参；同步 `long_term_ctx` 等调用点，跑绿 3.1
- [x] 3.3 跑既有 memory 单测/检索测试确认 user-scoping 行为不变

## 4. 清 3b-2 遗留死码

- [x] 4.1 删孤儿 `session/migrations.py`（其 sessions DDL 已 inline 进 `agent_state_migrations.py`）；`tests/integration/test_session_agent_migrations.py` 重指向 `agent_state_migrations`（或删，由 1.1 的统一列表测试覆盖）；全仓 grep 确认无残留引用 `session.migrations`

## 5. 收尾

- [x] 5.1 不得 import platform、无新增裸 sqlite3.connect、named params；依赖护栏
- [x] 5.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate per-agent-memory-lib --strict`
