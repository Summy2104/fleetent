## 0. 前置确认

- [ ] 0.1 确认本 change 只做 agent 到 KB 的绑定和解析，不做 Admin UI / HTTP endpoint
- [ ] 0.2 确认绑定关系存 SQLite，不放 `settings.yaml`
- [ ] 0.3 确认没有显式绑定时只访问默认 KB，不访问全部 KB
- [ ] 0.4 确认允许绑定暂不存在的 KB
- [ ] 0.5 确认默认 KB 缺失时降级为空 KB 范围，不阻断 agent 对话

## 1. Binding public API and schema

- [ ] 1.1 Write failing tests: `AgentKnowledgeBaseBinding`、`bind_agent_to_kb()`、
  `unbind_agent_from_kb()`、`list_agent_kb_bindings()`、`resolve_agent_kb_ids()` 可从
  `fleetent.intelligence.knowledge_base` public API 导入
- [ ] 1.2 Write failing tests: Alembic upgrade 到 head 后包含 `knowledge_base_agent_bindings` 表和
  `tenant_id + agent_id + kb_id` 唯一约束
- [ ] 1.3 Implement: 新增 binding dataclass、store/API skeleton、Alembic migration 和 public exports
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_agent_bindings.py -x -q`

## 2. Binding behavior

- [ ] 2.1 Write failing tests: `bind_agent_to_kb()` 重复调用幂等
- [ ] 2.2 Write failing tests: `unbind_agent_from_kb()` 对不存在绑定幂等
- [ ] 2.3 Write failing tests: tenant 隔离，不同 tenant 的同名 agent 绑定互不影响
- [ ] 2.4 Write failing tests: agent 隔离，同一 tenant 下不同 agent 绑定互不影响
- [ ] 2.5 Write failing tests: 空 `tenant_id`、`agent_id` 或 `kb_id` fail fast
- [ ] 2.6 Write failing tests: 可以绑定当前不存在的 `kb_id`
- [ ] 2.7 Implement: binding CRUD 行为和输入校验
- [ ] 2.8 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_agent_bindings.py -x -q`

## 3. KB scope resolution

- [ ] 3.1 Write failing tests: 显式绑定存在时，`resolve_agent_kb_ids()` 返回绑定 KB，不返回默认 KB
- [ ] 3.2 Write failing tests: 没有显式绑定时，`resolve_agent_kb_ids()` 返回
  `Settings.knowledge_base.default_kb_id`
- [ ] 3.3 Write failing tests: 默认 KB 未配置或为空时，`resolve_agent_kb_ids()` 返回空列表
- [ ] 3.4 Write failing tests: 默认 KB 缺失或解析为空时记录可诊断事件，不包含 query 或文档内容
- [ ] 3.5 Implement: scope resolution and diagnostics
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_base_agent_bindings.py -x -q`

## 4. Long-term context integration

- [ ] 4.1 Write failing tests: long-term-ctx built-in knowledge provider 调用
  `knowledge_base.resolve_agent_kb_ids(tenant_id, agent_id)`
- [ ] 4.2 Write failing tests: provider 把解析出的多个 KB 传给 `knowledge_base.search()`
- [ ] 4.3 Write failing tests: 解析结果为空时不调用 `knowledge_base.search()`，并保持 memory / empty context 降级
- [ ] 4.4 Implement: long-term-ctx provider integration
- [ ] 4.5 Verify green: 运行 `uv run pytest tests/integration/test_long_term_context_runtime.py -x -q`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/capabilities/knowledge-base.md`
- [ ] 5.2 更新 `docs/capabilities/long-term-ctx.md`
- [ ] 5.3 更新 `docs/capabilities/observability.md` 或相关诊断事件说明
- [ ] 5.4 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 5.5 运行 `uv run ruff format src tests`
- [ ] 5.6 运行 `uv run ruff check src tests`
- [ ] 5.7 运行 `uv run mypy src`
- [ ] 5.8 运行 `uv run pytest -x -q`
- [ ] 5.9 运行 `openspec validate knowledge-base-agent-kb-binding --strict`
- [ ] 5.10 运行 `git diff --check`
