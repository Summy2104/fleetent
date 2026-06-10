## 1. router 泛化（tenant_scope + agent_scope）

- [x] 1.1 写失败测试：`agent_scope(tenant, agent_id)` 返回 `AgentScope{state_db, vector_backend}`；SQLite 后端映射到 `<tenant>/<agent_id>/agent_state.db` + `agent_vectors.db`；与 `tenant_scope` 平级、不嵌套；后端可替换（注入假后端验调用点不变）
- [x] 1.2 实现：`tenant_router` 中 `scope`→`tenant_scope` 重命名 + 新增 `agent_scope` + `AgentScope` + `SQLiteTenantBackend` 的 per-agent 路径计算，跑绿 1.1
- [x] 1.3 同步 KB 侧所有 `router.scope(...)` 调用点改 `tenant_scope`；全仓 grep 确认无残留 `.scope(`；跑既有 KB 路由测试见绿

## 2. per-agent 库的 MIGRATIONS（session 元数据 DDL lift）

- [x] 2.1 写失败测试：空 per-agent 库经 Y 迁移后，含 `session/index.py` 现 `ensure_schema` 所建的元数据表（`sessions` 等运行表），结构等价
- [x] 2.2 实现：把 `session/index.py` 的 DDL 原样 lift 成 per-agent 库 `MIGRATIONS`（v1），跑绿 2.1（不改 schema，仅搬迁）

## 3. session 元数据连接走 agent_scope + boot 接线

- [x] 3.1 写失败测试：session 元数据索引的连接来自 `agent_scope(...).state_db`（migrate-on-open）；护栏断言 `session/index.py` 无 `create_database(...)` 自连接全局库
- [x] 3.2 实现：`session/index.py` 连接改走 `agent_scope`；删其 `create_database` 自连接；`agent_app._init_agent_db_schema` 中 session 部分接线到 agent_scope + migrate-on-open，跑绿 3.1
- [x] 3.3 跑既有 session/index（元数据 upsert/查询/批量删/统计）测试确认行为不变（连接来源改、语义不改）；确认 traces/memory/reflection 仍走 ensure_schema、未被波及

## 4. 收尾、护栏与门禁

- [ ] 4.1 确认不得 `import fleetent.platform.*`、无新增裸 `sqlite3.connect`、SQL named parameters；跑依赖护栏 + `scripts/check_module_boundaries.py` 相关
- [ ] 4.2 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate agent-scoped-db-routing --strict`
