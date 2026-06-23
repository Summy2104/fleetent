## 1. 表与迁移：agent_memory_items（无 scope）

- [x] 1.1 写测试（unit）：嵌入式迁移建出 `agent_memory_items`，**无 `scope_type`/`scope_id` 列**；先见红
- [x] 1.2 实现：`shared_memory_migrations.py`→`agent_memory_migrations.py`，新版本建 `agent_memory_items`（去 scope 列）；旧表不保留（重建窗口）；令 1.1 见绿

## 2. memory 模块正名 + 去 scope API

- [x] 2.1 写测试（unit）：`create_agent_memory(...)` / `search_agent_memory(query)` / `list_agent_memory()` / `iter_indexable_agent_memories()` **无 scope 参数**，读写经注入的 per-agent 库；`AgentMemoryItem` 无 scope 字段；先见红
- [x] 2.2 实现：`memory/shared.py`→`agent_memory.py`，函数/类/`set_*_db` 正名、去 scope 参数；向量命名空间去 scope 维（固定前缀）；令 2.1 见绿
- [x] 2.3 实现：`memory/__init__.py` 导出改名；`memory/models.py` `SharedMemoryItem`→`AgentMemoryItem`（去 scope）；`memory/proposal_store.py`、`memory/trends.py` 同步正名/去 scope
- [x] 2.4 跑 `memory` 既有单测 + 护栏 `test_module_dependency_guardrails`（`memory ↛ reflection`）确认仍绿

## 3. 路由：agent_scope 提供 agent memory（移出 tenant_scope）

- [x] 3.1 写测试（unit/integration）：`agent_scope(tenant, agent_id)` 暴露 agent memory 句柄；`tenant_scope` **不再**有 `open_shared_memory_db`；先见红
- [x] 3.2 实现：`tenant_router.py` 删 `open_shared_memory_db`，在 `AgentScope` 加 agent memory open；令 3.1 见绿
- [x] 3.3 写测试（integration）：`_init_agent_db_schema` 后 home 下有 per-agent `agent_memory.db`、**无 `shared_memory.db`**；先见红→实现（`agent_app._init_agent_db_schema` 经 `agent_scope` 建）见绿

## 4. reflection 与 platform 投影对齐

- [x] 4.1 实现：reflection `suggest_shared_memory_or_kb` 术语改 agent_memory（promote-to-KB 出路不变）；`apply_shared_memory_proposal`→`apply_agent_memory_proposal`；更新相关测试
- [x] 4.2 写测试（integration）：platform read-projection 对 agent memory 改 **per-agent 直读**（读该 agent 的 agent memory 只读库，不 per-tenant、不跨 agent）；先见红→实现 `platform/read_projection.py` 见绿
- [x] 4.3 `config.py` 若有 shared-memory 设置项，正名/去 scope

## 5. 收尾

- [ ] 5.1 全库 grep 残留 `shared_memory`/`SharedMemory`/`scope_type.*shared` 清零（`vector_store/reindex.py` 等）；无遗漏
- [ ] 5.2 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import 违规
- [ ] 5.3 文档：若最终采纳 D5 折叠方案，同步更新 `docs/architecture/agent-home-layout.md` 目标态树（非代码产物，人工确认后再 commit）
- [ ] 5.4 change 收尾：`make test-pr` + `make test-unit-ci`（覆盖率门禁）全绿，对照 main 无新增失败；相关 memory/tenant_router/platform integration 测试无新增失败
