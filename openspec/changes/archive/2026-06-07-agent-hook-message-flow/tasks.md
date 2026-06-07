## 1. on_user_input 集成（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_hook_on_user_input.py`）：`deny`→run_stream yield error 并终止；`modified_content`→user_input 被替换；`hooks_enabled=False` 或无注册→零行为变化。看红
- [x] 1.2 实现：在 `run_stream()` user_input 字符串进 messages 前 dispatch `on_user_input`；`deny`→yield error + return；`modified_content`→替换 user_input；`inject_context`→追加消息。看绿

## 2. pre_llm_call 集成（TDD）

- [x] 2.1 写失败测试（`tests/unit/test_hook_pre_llm_call.py`）：`inject_context`→messages 末尾追加了 user 消息再调 LLM；`None`→messages 无变化；`hooks_enabled=False` 或无注册→零行为变化。看红
- [x] 2.2 实现：在 `run()` 的 `sanitize` 后、`_call_with_overflow_retry` 前 dispatch `pre_llm_call`，`inject_context` 追加到 messages；`run_stream()` 同位置。看绿

## 3. on_assistant_reply 集成（TDD）

- [x] 3.1 写失败测试（`tests/unit/test_hook_on_assistant_reply.py`）：`modified_content`→run() 返回改写后的 reply；tool_calls turn 不触发；`hooks_enabled=False` 或无注册→零行为变化。看红
- [x] 3.2 实现：在 `run()` 的 `messages.append(msg.model_dump())` 前（仅 content 非空 turn）dispatch `on_assistant_reply`，`modified_content` 替换 content；`run_stream()` 在 `reply = "".join(reply_parts)` 后 break 前同样处理。看绿

## 4. normalizer on_user_input（TDD）

- [x] 4.1 写测试（`tests/integration/test_hook_normalizer.py`）：IM normalizer 路径 `deny`→历史不追加用户消息、不调 run；`modified_content`→历史追加改写后的内容。看绿
- [x] 4.2 实现：在 `normalizer.route` 的 `user_content` 构建后、`history.append(user)` 前 dispatch；`deny`→回 IM 提示并 return；`modified_content`→替换 user_content。看绿

## 5. 收尾

- [x] 5.1 `uv run ruff format` + `ruff check` + `mypy src` + `check_test_layers` + 全量 `uv run pytest -x -q`。看绿
