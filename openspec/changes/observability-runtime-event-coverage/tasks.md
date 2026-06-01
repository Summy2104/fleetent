## 0. 前置确认

- [x] 0.1 确认本 change 只补 runtime trace events，不做 performance rollup API
- [x] 0.2 确认不新增 trace table，不引入 OpenTelemetry SDK
- [x] 0.3 确认 payload 只保存摘要、计数、耗时和截断标记，不保存完整 prompt / reply / tool result

## 1. Run lifecycle events

- [x] 1.1 Write failing tests: `agent_loop.run()` 记录 `agent_run_started`
- [x] 1.2 Write failing tests: `agent_loop.run_stream()` 记录 `agent_run_started`
- [x] 1.3 Write failing tests: runtime exception 记录 `agent_run_failed`
- [x] 1.4 Implement: 在 non-streaming / streaming 路径接入 run lifecycle events
- [x] 1.5 Verify green: 运行 `uv run pytest tests/integration/test_agent_loop.py -x -q`

## 2. LLM call and fallback events

- [x] 2.1 Write failing tests: 每次 LLM 调用记录 `llm_call_started` 和 `llm_call_completed`
- [x] 2.2 Write failing tests: LLM 调用失败记录 `llm_call_failed`
- [x] 2.3 Write failing tests: fallback 切换记录 `model_fallback_triggered`
- [x] 2.4 Implement: 为 `_call_with_fallback()` / `_stream_with_fallback()` 增加事件覆盖
- [x] 2.5 Verify green: 运行 `uv run pytest tests/integration/test_agent_loop.py -x -q`

## 3. Tool call events

- [x] 3.1 Write failing tests: 工具调用记录 `tool_call_started` 和 `tool_call_completed`
- [x] 3.2 Write failing tests: 工具异常或 dispatch 失败记录 `tool_call_failed`
- [x] 3.3 Write failing tests: streaming path 的工具调用也记录相同事件
- [x] 3.4 Implement: 为普通工具和 sub_agent 工具接入事件覆盖
- [x] 3.5 Verify green: 运行 `uv run pytest tests/integration/test_agent_loop.py -x -q`

## 4. Permission and context events

- [x] 4.1 Write failing tests: medium/high risk 工具请求审批时记录 `permission_requested`
- [x] 4.2 Write failing tests: 审批 approved / rejected / timeout 后记录 `permission_resolved`
- [x] 4.3 Write failing tests: 触发上下文压缩时记录 `context_compression_completed`
- [x] 4.4 Implement: 接入 permission 和 context compression 事件
- [x] 4.5 Verify green: 运行 `uv run pytest tests/integration/test_agent_loop.py -x -q`

## 5. Final reply and contract tests

- [x] 5.1 Write failing tests: final non-streaming reply 记录 `final_reply_emitted`
- [x] 5.2 Write failing tests: streaming done 前后记录 `final_reply_emitted`
- [x] 5.3 Write failing tests: contract test 断言同一次 run 的 runtime events 共享 run_id
- [x] 5.4 Implement: final reply event 和跨事件 run_id 关联
- [x] 5.5 Verify green: 运行 `uv run pytest tests/integration/test_agent_loop.py tests/integration/test_trace_events.py -x -q`

## 6. Docs and final verification

- [x] 6.1 更新 `docs/capabilities/observability.md`
- [x] 6.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 6.3 运行 `uv run ruff format src tests`
- [x] 6.4 运行 `uv run ruff check src tests`
- [x] 6.5 运行 `uv run mypy src`
- [x] 6.6 运行 `uv run pytest -x -q`
- [x] 6.7 运行 `openspec validate observability-runtime-event-coverage`
- [x] 6.8 运行 `git diff --check`
