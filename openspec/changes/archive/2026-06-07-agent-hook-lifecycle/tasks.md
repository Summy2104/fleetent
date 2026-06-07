## 1. pre_compact + post_compact（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_hook_pre_compact.py`）：`pre_compact` inject_context→注入内容追加到压缩前 messages；`post_compact` 观测→payload 含 messages_before/after；`hooks_enabled=False`→零行为变化。看红
- [x] 1.2 实现：在 `run()` 和 `run_stream()` 的 `_gated_compress` 前 dispatch `pre_compact`，inject_context 追加到 messages；`_gated_compress` 后 dispatch `post_compact`，payload 含压缩前后消息数。看绿

## 2. on_run_complete（TDD）

- [x] 2.1 写失败测试（`tests/unit/test_hook_on_run_complete.py`）：hook 被调用且 payload 含 reply；`hooks_enabled=False`→不调用；hook 的返回值不影响 reply。看红
- [x] 2.2 实现：在 `run()` 的 `_apply_output_transform` 后、`return reply` 前 dispatch `on_run_complete`。看绿

## 3. session_start + session_end（TDD）

- [x] 3.1 写失败测试（`tests/integration/test_hook_session_lifecycle.py`）：`session_start` inject_context→history 追加上下文；`session_end`→reply 传入 payload；`hooks_enabled=False`→零变化。看红
- [x] 3.2 实现：在 `normalizer.route` 的 history 加载后 dispatch `session_start`；`run()` 返回后 dispatch `session_end`。看绿

## 4. 收尾

- [x] 4.1 `ruff format` + `ruff check` + `mypy src` + `check_test_layers` + 全量 `uv run pytest -x -q`。看绿
