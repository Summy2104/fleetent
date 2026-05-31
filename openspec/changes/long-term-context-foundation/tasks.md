## 0. 前置确认

- [ ] 0.1 确认本 change 不实现 knowledge-base 运行时代码
- [ ] 0.2 确认本 change 不新增数据库表
- [ ] 0.3 确认 knowledge-base 在本 change 中是 optional/null provider

## 1. Public model 与空预算行为

- [ ] 1.1 Write failing tests: `BuiltContext`、`ContextSource` 和 `build_context` 可导入
- [ ] 1.2 Write failing tests: `available_tokens <= 0` 时返回空 text 和空 sources，且不调用任何 provider
- [ ] 1.3 实现 public model、public API 和空预算短路
- [ ] 1.4 运行 `uv run pytest -x -q`，确认 1.1/1.2 红测转绿

## 2. Memory provider 接入

- [ ] 2.1 Write failing tests: `build_context()` 调用 memory-layer `search(user_id, query, limit)`
- [ ] 2.2 Write failing tests: memory 返回结果时输出 memory 区段和 `source_type="memory"` 来源摘要
- [ ] 2.3 实现 memory provider 查询、格式化和 source summary
- [ ] 2.4 运行 `uv run pytest -x -q`，确认 2.1/2.2 红测转绿

## 3. Knowledge optional/null provider

- [ ] 3.1 Write failing tests: KB provider 缺失或 disabled 时不报错，仍返回 memory context
- [ ] 3.2 Write failing tests: KB provider 返回空结果时不输出 knowledge 区段
- [ ] 3.3 实现 optional/null knowledge provider 边界
- [ ] 3.4 运行 `uv run pytest -x -q`，确认 3.1/3.2 红测转绿

## 4. 合并、排序与 token 预算

- [ ] 4.1 Write failing tests: memory 与 knowledge 均有结果时，输出两个区段并返回两个来源摘要
- [ ] 4.2 Write failing tests: 超出 token 预算时截断低优先级内容，memory 优先保留
- [ ] 4.3 实现合并、稳定排序和预算截断
- [ ] 4.4 运行 `uv run pytest -x -q`，确认 4.1/4.2 红测转绿

## 5. agent-runtime 接入

- [ ] 5.1 Write failing tests: `agent_loop.run()` / `run_stream()` / `run_sync()` 在构造 prompt 前调用 `build_context`
- [ ] 5.2 Write failing tests: `BuiltContext.text` 为空时不追加长期上下文区段
- [ ] 5.3 修改 agent-runtime 接入 long-term-ctx
- [ ] 5.4 运行 `uv run pytest -x -q`，确认 5.1/5.2 红测转绿

## 6. 收尾验证

- [ ] 6.1 运行 `uv run pytest -x -q`
- [ ] 6.2 运行 `uv run ruff format src tests`
- [ ] 6.3 运行 `uv run ruff check src tests`
- [ ] 6.4 运行 `uv run mypy src`
- [ ] 6.5 运行 `openspec validate long-term-context-foundation`
