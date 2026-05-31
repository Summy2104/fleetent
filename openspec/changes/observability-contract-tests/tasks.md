## 0. 前置确认

- [ ] 0.1 确认本 change 只补 observability contract tests，不改变运行时行为
- [ ] 0.2 确认测试使用 tmp SQLite DB，不触碰 `data/`
- [ ] 0.3 确认现有单元测试保留，新增测试聚焦端到端 contract

## 1. Non-streaming run contract

- [ ] 1.1 Write failing tests: `agent_loop.run()` 写入 `injected_context` 和 `agent_run_completed`
- [ ] 1.2 Write failing tests: 两类事件共享同一个 `run_id`
- [ ] 1.3 Write failing tests: `query_trace_events()` 可按 run_id / event_type 查询两类事件
- [ ] 1.4 如测试暴露 contract bug，做最小修复
- [ ] 1.5 运行 `uv run pytest -x -q`，确认 1.1-1.3 红测转绿

## 2. Streaming run contract

- [ ] 2.1 Write failing tests: `agent_loop.run_stream()` 写入 `injected_context` 和 `agent_run_completed`
- [ ] 2.2 Write failing tests: streaming path 两类事件共享同一个 `run_id`
- [ ] 2.3 如测试暴露 contract bug，做最小修复
- [ ] 2.4 运行 `uv run pytest -x -q`，确认 2.1/2.2 红测转绿

## 3. Payload safety contract

- [ ] 3.1 Write failing tests: source attribution payload 不保存完整 `content` / `text` / `transcript`
- [ ] 3.2 Write failing tests: sensitive payload values 被 redaction
- [ ] 3.3 Write failing tests: large payload values 被 truncation 并带截断标记
- [ ] 3.4 如测试暴露 contract bug，做最小修复
- [ ] 3.5 运行 `uv run pytest -x -q`，确认 3.1-3.3 红测转绿

## 4. Usage aggregation contract

- [ ] 4.1 Write failing tests: usage summary 只统计 `agent_run_completed`
- [ ] 4.2 Write failing tests: 同一 run 存在 `injected_context` 时不会影响 run_count / token totals
- [ ] 4.3 如测试暴露 contract bug，做最小修复
- [ ] 4.4 运行 `uv run pytest -x -q`，确认 4.1/4.2 红测转绿

## 5. 收尾验证

- [ ] 5.1 运行 `uv run pytest -x -q`
- [ ] 5.2 运行 `uv run ruff format src tests`
- [ ] 5.3 运行 `uv run ruff check src tests`
- [ ] 5.4 运行 `uv run mypy src`
- [ ] 5.5 运行 `openspec validate observability-contract-tests`
