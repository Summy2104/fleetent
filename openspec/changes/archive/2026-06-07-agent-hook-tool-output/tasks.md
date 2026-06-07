## 1. post_tool_use 集成（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_hook_post_tool_use.py`，复用 mock_client + 注册 post_tool_use hook + 启用 hooks via governance）：`modified_content`→LLM 收到改写后的工具结果；`None`→结果原样进 messages；`hooks_enabled=False` 或无注册→零行为变化；placeholder slot 不触发 hook。看红
- [x] 1.2 实现：`_backfill_slots` 改 async；`run()` 处改为 `await _backfill_slots(...)`；backfill 内对非 placeholder slot 在 content 追加前 dispatch `post_tool_use`，`modified_content` 替换 content；run_stream 内联 backfill 同理（已在 async context）。看绿

## 2. output_transform 集成（TDD）

- [x] 2.1 写失败测试（`tests/unit/test_hook_output_transform.py`，复用 mock_client + 注册 output_transform hook + 启用 hooks via governance）：`modified_content`→返回改写后 reply；`None`→reply 原样；`hooks_enabled=False` 或无注册→零行为变化。看红
- [x] 2.2 实现：提取 `_apply_output_transform(reply, governance, session_id, agent_name, user_id) -> str` 内联 helper；在 `run()` 的两处 `return reply`（1469 + 1661）前 await；在 `run_stream()` 的两处 `yield done`（early-exit + 正常）前 await 并用结果。看绿

## 3. 收尾

- [x] 3.1 `uv run ruff format src tests`（仅改动）、`uv run ruff check src tests`、`uv run mypy src`、`uv run python scripts/check_test_layers.py`、全量 `uv run pytest -x -q`。看绿
