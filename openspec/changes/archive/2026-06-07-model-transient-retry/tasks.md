## 1. 退避重试 helper（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_transient_retry.py`，patch `_backoff_delay`→0）：瞬时(429)首败后重试成功；非瞬时(ValueError/auth)立即抛；持续 429 至 cap 后抛（调用次数=cap+1）；context_overflow 不重试（调用 1 次）。看红
- [x] 1.2 实现 `_create_with_transient_retry` + `_retry_after_seconds` + `_backoff_delay`（`import random`）。看绿

## 2. 接入两路 + 收尾

- [x] 2.1 把 `_call_policy_chat` 与 `_stream_policy_chat` 的 create 调用包进 `_create_with_transient_retry`（既有 failover except 不变）。运行现有 agent_loop / model 测试无回归。
- [x] 2.2 `uv run ruff format`（改动）、`ruff check`（改动）、`mypy src/fleetent/runtime/loop.py`、全量 `uv run pytest -x -q`；`openspec validate model-transient-retry --strict`。
