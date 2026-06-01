## 0. 前置确认

- [x] 0.1 确认本 change 只做 Python public API，不做 HTTP / admin CLI / dashboard
- [x] 0.2 确认不新增 rollup 表，不直接 SQL 查询 traces
- [x] 0.3 确认依赖已归档的 `observability-runtime-event-coverage` 产出的 runtime events

## 1. Public API shape

- [x] 1.1 Write failing tests: `PerformanceQuery`、`PerformanceSummary` 和 `get_performance_summary()` 可从 `fleetent.observability` 导入
- [x] 1.2 Write failing tests: 空 trace 返回全 0 summary
- [x] 1.3 Implement: 新增 performance summary dataclasses 和 public exports
- [x] 1.4 Verify green: 运行 `uv run pytest tests/integration/test_performance_summary.py -x -q`

## 2. Run-level metrics

- [x] 2.1 Write failing tests: 聚合 terminal events `agent_run_completed` 和 `agent_run_failed`
- [x] 2.2 Write failing tests: 计算 run_count、completed_count、failed_count、failure_rate，其中 run_count = completed_count + failed_count
- [x] 2.3 Write failing tests: 计算 avg_elapsed_s、p50_elapsed_s、p95_elapsed_s
- [x] 2.4 Implement: run-level aggregation and percentile helper
- [x] 2.5 Verify green: 运行 `uv run pytest tests/integration/test_performance_summary.py -x -q`

## 3. LLM and fallback metrics

- [x] 3.1 Write failing tests: 聚合 `llm_call_completed` / `llm_call_failed`
- [x] 3.2 Write failing tests: 聚合 `model_fallback_triggered`
- [x] 3.3 Write failing tests: 按 model 生成调用次数、失败次数、平均耗时
- [x] 3.4 Implement: LLM / fallback aggregation
- [x] 3.5 Verify green: 运行 `uv run pytest tests/integration/test_performance_summary.py -x -q`

## 4. Tool and permission metrics

- [x] 4.1 Write failing tests: 聚合 `tool_call_completed` / `tool_call_failed`
- [x] 4.2 Write failing tests: 按 tool_name 生成调用次数、失败次数、平均耗时
- [x] 4.3 Write failing tests: 聚合 `permission_requested` / `permission_resolved` 的 approved / rejected / timeout 和等待耗时
- [x] 4.4 Implement: tool / permission aggregation
- [x] 4.5 Verify green: 运行 `uv run pytest tests/integration/test_performance_summary.py -x -q`

## 5. Filters and tolerance

- [x] 5.1 Write failing tests: 支持 user_id、agent_id、tenant_id、session_id、start_ts、end_ts、limit 过滤
- [x] 5.2 Write failing tests: session_id 过滤在读取 trace API 后按 `TraceEvent.session_id` 过滤，不要求 `TraceQuery` 新增 session_id 字段
- [x] 5.3 Write failing tests: 缺失字段、非法 elapsed、旧 trace 和不完整事件流不抛错
- [x] 5.4 Implement: filtering through `query_trace_events()` and tolerant payload parsing
- [x] 5.5 Verify green: 运行 `uv run pytest tests/integration/test_performance_summary.py -x -q`

## 6. Docs and final verification

- [x] 6.1 更新 `docs/capabilities/observability.md`
- [x] 6.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 6.3 运行 `uv run ruff format src tests`
- [x] 6.4 运行 `uv run ruff check src tests`
- [x] 6.5 运行 `uv run mypy src`
- [x] 6.6 运行 `uv run pytest -x -q`
- [x] 6.7 运行 `openspec validate observability-performance-summary`
- [x] 6.8 运行 `git diff --check`
