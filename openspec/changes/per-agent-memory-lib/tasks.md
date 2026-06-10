## 1. memory schema 迁 per-agent 库（去 namespace 列）

- [ ] 1.1 写失败测试：空 per-agent 库经 Y 迁移后含 `memory_items` 表、**不含 `namespace` 列**，其余结构等价于现 `memory/store.py` ensure_schema
- [ ] 1.2 实现：lift `memory_items` DDL（去 namespace 列）进 per-agent `MIGRATIONS`（接 3b-1 之后），跑绿 1.1

## 2. 连接走 agent_scope + 接线

- [ ] 2.1 写失败测试：memory store 连接来自 `agent_scope(...).state_db`；护栏断言无 `create_database`/`ensure_schema`-into-global 残留
- [ ] 2.2 实现：memory/store.py 连接走 agent_scope；删自连接；`agent_app._init_agent_db_schema` 接线，跑绿 2.1

## 3. 去 namespace 第二参（R2-叉2）

- [ ] 3.1 写失败测试：`memory_namespace(user_id)` 单参返回 `mem:{user_id}`；memory `search`/`extract_and_update` 签名无 `namespace` 参
- [ ] 3.2 实现：删 `memory_namespace` 第二参 + memory 操作的 `namespace` 参；同步 `long_term_ctx` 等调用点，跑绿 3.1
- [ ] 3.3 跑既有 memory 单测/检索测试确认 user-scoping 行为不变

## 4. 收尾

- [ ] 4.1 不得 import platform、无新增裸 sqlite3.connect、named params；依赖护栏
- [ ] 4.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate per-agent-memory-lib --strict`
