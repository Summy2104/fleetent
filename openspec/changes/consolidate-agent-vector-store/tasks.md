## 1. 路由：单一 per-agent 向量后端

- [ ] 1.1 写测试（unit/integration）：`agent_scope(T,A)` 返回的 `AgentScope` **只有** `state_db` + `vector_backend`（无 `agent_memory_vector_backend`）；`vector_backend` 指向 `agent_vectors.db`；先见红
- [ ] 1.2 实现：`tenant_router.resolve_agent` 只构造一个 `SQLiteVectorBackend(agent_vectors.db)`；`AgentScope` 删 `agent_memory_vector_backend` 字段；不再构造 `agent_memory_vectors.db`；令 1.1 见绿

## 2. 接线：同一 backend 注入两处

- [ ] 2.1 写测试（unit/integration）：`agent_app._init_agent_db_schema` 后，user memory 与 agent memory 经**同一** vector backend（`agent_vectors.db`）读写；先见红
- [ ] 2.2 实现：`_init_agent_db_schema` 把单一 `vector_backend` 注入 `memory.store.set_vector_backend` 与 `agent_memory.set_agent_memory_db(state_db, vb)`；令 2.1 见绿

## 3. namespace 隔离回归

- [ ] 3.1 写测试（unit）：同库内 user memory（`mem:{user_id}`）与 agent memory（`agentmem:`）向量互不可见——`search_agent_memory` 搜不到 user memory 向量，user memory `search` 搜不到 agent memory 向量；先见红→（应天然绿，因 namespace 过滤）确认
- [ ] 3.2 跑 memory / long_term_ctx 既有向量相关测试，确认 user memory + agent memory 检索无回归

## 4. 收尾

- [ ] 4.1 boot 一个 agent 后确认：`agent_vectors.db` 存在且容 `mem:`+`agentmem:` namespace；**无** `agent_memory_vectors.db`
- [ ] 4.2 grep 残留 `agent_memory_vectors`、`agent_memory_vector_backend` 引用清零（src+tests）
- [ ] 4.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包违规；护栏 `test_module_dependency_guardrails`（memory↛reflection / agent↛platform）仍绿
- [ ] 4.4 change 收尾：`make test-pr` + `make test-unit-ci`（覆盖率门禁）全绿，对照 main 无新增失败；相关 memory/tenant_router integration 无新增失败
