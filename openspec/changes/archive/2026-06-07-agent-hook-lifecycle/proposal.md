## Why

P1–P3 已覆盖工具链和消息流的所有钩子点。P4 补全生命周期维度：压缩前/后（合规注入 + 审计）、run 完成（审计/通知/计费）、会话起止（企业上下文初始化/清理）。

## What Changes

- `pre_compact`：在 `loop.py` 的 `_gated_compress` 前 dispatch，`inject_context`→压缩前追加必保留内容；纯观测返回 None。
- `post_compact`：`_gated_compress` 后、`messages[:] = _compressed` 赋值后 dispatch，纯观测（payload: 压缩前后消息数）。
- `on_run_complete`：`run()` 结束前（`_record_agent_run_completed` 调用后、`return reply` 前）dispatch，纯观测（payload: reply, stop_reason）。
- `session_start`：`normalizer.route` 中 `session_lock` 内、`history` 加载后 dispatch，`inject_context`→向 history 首条 user 消息前注入上下文。
- `session_end`：`normalizer.route` 中 `run()` 完成后、session 保存前 dispatch，纯观测（payload: session_id, reply）。

## Capabilities

### New Capabilities

- `agent-hook-pre-compact`: 压缩前注入与观测钩子点
- `agent-hook-post-compact`: 压缩后观测钩子点
- `agent-hook-on-run-complete`: run 完成观测钩子点
- `agent-hook-session-lifecycle`: 会话起止钩子点（session_start / session_end）

### Modified Capabilities

（无）

## Impact

- `src/fleetent/runtime/loop.py`：`pre_compact` + `post_compact` + `on_run_complete`
- `src/fleetent/im_gateway/normalizer.py`：`session_start` + `session_end`
- `tests/unit/test_hook_pre_compact.py`（新建）
- `tests/unit/test_hook_on_run_complete.py`（新建）
- `tests/integration/test_hook_session_lifecycle.py`（新建）
