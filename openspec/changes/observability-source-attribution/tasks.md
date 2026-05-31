## 0. 前置确认

- [ ] 0.1 确认 `long-term-context-foundation` 已完成并归档
- [ ] 0.2 确认本 change 复用现有 `traces` 表，不新增表
- [ ] 0.3 确认本 change 不保存完整 memory / KB content
- [ ] 0.4 确认本 change 不实现 knowledge-base 运行时代码

## 1. Public model 与 API

- [ ] 1.1 Write failing tests: `InjectedContextTrace` 和 `record_injected_context` 可从 `fleetent.observability` 导入
- [ ] 1.2 Write failing tests: `InjectedContextTrace` 包含 source_id、source_type、score、token_estimate、metadata
- [ ] 1.3 实现 public model 和 public API
- [ ] 1.4 运行 `uv run pytest -x -q`，确认 1.1/1.2 红测转绿

## 2. injected_context trace event

- [ ] 2.1 Write failing tests: `record_injected_context(run_id, sources)` 写入 `event_type="injected_context"` trace event
- [ ] 2.2 Write failing tests: payload 包含 sources summary，不包含 `content`、`text`、`transcript`
- [ ] 2.3 实现 source summary 到 TraceEvent payload 的转换
- [ ] 2.4 运行 `uv run pytest -x -q`，确认 2.1/2.2 红测转绿

## 3. 空 sources 跳过

- [ ] 3.1 Write failing tests: sources 为空时不调用 `record_trace_event()`
- [ ] 3.2 实现空 sources 短路
- [ ] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. agent-runtime 接入

- [ ] 4.1 Write failing tests: `agent_loop.run()` 为一次 run 生成稳定 run_id，并让 injected_context 与 agent_run_completed 使用同一个 run_id
- [ ] 4.2 Write failing tests: `agent_loop.run_stream()` 为一次 run 生成稳定 run_id，并让 injected_context 与 agent_run_completed 使用同一个 run_id
- [ ] 4.3 Write failing tests: `agent_loop.run()` 注入 long-term context 后调用 `record_injected_context()`
- [ ] 4.4 Write failing tests: `agent_loop.run_stream()` 注入 long-term context 后调用 `record_injected_context()`
- [ ] 4.5 Write failing tests: `BuiltContext.sources` 为空时 agent-runtime 不写 injected_context event
- [ ] 4.6 修改 agent-runtime 接入 source attribution，并复用同一 run_id
- [ ] 4.7 运行 `uv run pytest -x -q`，确认 4.1-4.5 红测转绿

## 5. 查询与安全

- [ ] 5.1 Write failing tests: `query_trace_events(TraceQuery(event_type="injected_context"))` 可查到来源归因事件
- [ ] 5.2 Write failing tests: metadata 中敏感值经过现有 trace payload 脱敏
- [ ] 5.3 确认复用 trace query 与 payload safety，不绕过 `record_trace_event()`
- [ ] 5.4 运行 `uv run pytest -x -q`，确认 5.1/5.2 红测转绿

## 6. 收尾验证

- [ ] 6.1 运行 `uv run pytest -x -q`
- [ ] 6.2 运行 `uv run ruff format src tests`
- [ ] 6.3 运行 `uv run ruff check src tests`
- [ ] 6.4 运行 `uv run mypy src`
- [ ] 6.5 运行 `openspec validate observability-source-attribution`
