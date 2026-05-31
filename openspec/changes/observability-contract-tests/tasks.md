## 0. 前置确认

- [x] 0.1 确认本 change 只补 observability contract tests，不改变运行时行为
- [x] 0.2 确认测试使用 tmp SQLite DB，不触碰 `data/`
- [x] 0.3 确认现有单元测试保留，新增测试聚焦端到端 contract
- [x] 0.4 确认 `test-suite-organization` 已完成或已合入当前工作树，新增测试放在 `tests/integration/`
- [x] 0.5 确认不向平铺 `tests/` 根目录新增 observability contract test

## 1. Non-streaming run contract

- [x] 1.1 Write failing tests: `agent_loop.run()` 写入 `injected_context` 和 `agent_run_completed`
- [x] 1.2 Write failing tests: 两类事件共享同一个 `run_id`
- [x] 1.3 Write failing tests: `query_trace_events()` 可按 run_id / event_type 查询两类事件
- [x] 1.4 如测试暴露 contract bug，做最小修复
- [x] 1.5 运行 `uv run pytest tests/integration -x -q`，确认 1.1-1.3 红测转绿

## 2. Streaming run contract

- [x] 2.1 Write failing tests: `agent_loop.run_stream()` 写入 `injected_context` 和 `agent_run_completed`
- [x] 2.2 Write failing tests: streaming path 两类事件共享同一个 `run_id`
- [x] 2.3 如测试暴露 contract bug，做最小修复
- [x] 2.4 运行 `uv run pytest tests/integration -x -q`，确认 2.1/2.2 红测转绿

## 3. Payload safety contract

- [x] 3.1 Write failing tests: source attribution payload 不保存完整 `content` / `text` / `transcript`
- [x] 3.2 Write failing tests: sensitive payload values 被 redaction
- [x] 3.3 Write failing tests: large payload values 被 truncation 并带截断标记
- [x] 3.4 如测试暴露 contract bug，做最小修复
- [x] 3.5 运行 `uv run pytest tests/integration -x -q`，确认 3.1-3.3 红测转绿

## 4. Usage aggregation contract

- [x] 4.1 Write failing tests: usage summary 只统计 `agent_run_completed`
- [x] 4.2 Write failing tests: 同一 run 存在 `injected_context` 时不会影响 run_count / token totals
- [x] 4.3 如测试暴露 contract bug，做最小修复
- [x] 4.4 运行 `uv run pytest tests/integration -x -q`，确认 4.1/4.2 红测转绿

## 5. 收尾验证

- [x] 5.1 运行 `uv run pytest tests/integration -x -q`
- [x] 5.2 运行 `uv run pytest -x -q`
- [x] 5.3 运行 `uv run ruff format src tests`
- [x] 5.4 运行 `uv run ruff check src tests`
- [x] 5.5 运行 `uv run mypy src`
- [x] 5.6 运行 `openspec validate observability-contract-tests`
