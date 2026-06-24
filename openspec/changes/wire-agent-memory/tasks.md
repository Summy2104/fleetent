## 1. 关系库收编：agent_memory_items → agent_state.db

- [ ] 1.1 写测试（unit）：`AGENT_STATE_MIGRATIONS` 新版本建出 `agent_memory_items` 表（沿用列、无 scope 列）；先见红
- [ ] 1.2 实现：把 `agent_memory_items` 的 `CREATE TABLE` 加进 `runtime/agent_state_migrations.py` 新版本；删 `memory/agent_memory_migrations.py`；令 1.1 见绿
- [ ] 1.3 写测试（unit/integration）：`agent_scope` 不再暴露 `open_agent_memory_db`/`open_agent_memory_db_ro`；agent memory 关系经 `agent_state.db`；**保留** agentmem 向量 backend；先见红
- [ ] 1.4 实现：`tenant_router` 删 `open_agent_memory_db`/`open_agent_memory_db_ro`/`AgentScope.agent_memory_db` + `resolve_agent` 里 `agent_memory.db` 的 `create_substrate`（保留 `agent_memory_vector_backend`）；令 1.3 见绿
- [ ] 1.5 实现：`memory/agent_memory.py` `set_agent_memory_db` 关系操作改用 agent_state 连接；`agent_app._init_agent_db_schema` 接线改 agent_memory 关系走 `state_db`、向量仍接 agentmem backend
- [ ] 1.6 写测试（integration）：boot 后 `agent_state.db` 含 `agent_memory_items`，**无** `agent_memory.db`/`shared_memory.db`；agent_memory_vectors.db 仍独立；先见红→实现见绿

## 2. 写闭环：审批门 resolve → 真写 agent_memory

- [ ] 2.1 写测试（unit/integration）：批准一个 `target=agent_memory` proposal 并 resolve → `agent_memory_items` 真增一行（content=proposed_content，source=`reflection_proposal`，source_ref=proposal id）+ 向量可被 `search_agent_memory` 检索；proposal→`applied`；先见红
- [ ] 2.2 实现：`governance/reflection_gate` 的 agent_memory 分支编排 `memory.create_agent_memory(...)` 后标 applied（governance→memory 方向；不让 memory import reflection）；改 `mark_agent_memory_proposal_applied`/apply 路径真写；令 2.1 见绿
- [ ] 2.3 跑护栏 `tests/unit/test_module_dependency_guardrails.py`（`memory ↛ reflection`、agent↛platform）确认仍绿

## 3. 读闭环：build_context 第三源 + 独立预算档

- [ ] 3.1 写测试（unit）：`LongTermContextSettings` 含 `agent_memory_max_tokens`/`agent_memory_top_k`；`conflict_preference` 取三方值；先见红→实现 `config.py` 见绿
- [ ] 3.2 写测试（unit）：`build_context` 调 `search_agent_memory`（不传 user_id），命中时产出 `source_type="agent_memory"` 候选；空则省略区段；先见红
- [ ] 3.3 实现：`long_term_ctx/__init__.py` 加 agent_memory 检索 + `agent_memory_candidate` + 并入 `_ordered_candidates`/`_select_candidates`；`_select_candidates` 二元→三元（各源独立 `*_max_tokens`/`*_top_k`）；`_render_context` 加 agent_memory 区段；令 3.2 见绿
- [ ] 3.4 写测试（unit）：三源预算互不挤占（agent_memory 缺省预算不影响既有 memory/knowledge 行为）；conflict_preference 三方优先级；先见红→实现见绿
- [ ] 3.5 跑 long-term-ctx evaluation fixtures（`tests/evaluation`）确认确定性上下文无回归

## 4. 平台投影对齐

- [ ] 4.1 写测试（integration）：platform agent_memory 投影改读 `agent_state.db` 的 `agent_memory_items`（只读不迁移），不读独立 `agent_memory.db`；先见红→实现 `platform/read_projection.py` 见绿

## 5. 端到端 + 收尾

- [ ] 5.1 写测试（integration/e2e）：批准 agent_memory proposal → 后续对话 `build_context` 注入该 agent memory（trace 含 `source_type="agent_memory"`）；先见红→接通见绿
- [ ] 5.2 grep 残留：`agent_memory.db`、`open_agent_memory_db`、`agent_memory_migrations` 引用清零（src+tests）
- [ ] 5.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包违规
- [ ] 5.4 change 收尾：`make test-pr` + `make test-unit-ci`（覆盖率门禁）全绿，对照 main 无新增失败；相关 memory/long_term_ctx/tenant_router/platform integration 无新增失败
