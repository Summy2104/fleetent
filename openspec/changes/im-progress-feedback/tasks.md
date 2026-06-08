## 1. NormalizedMessage 扩展

- [x] 1.1 Write failing tests for NormalizedMessage.progress_func field: 在 tests/unit/ 新增测试，验证字段存在、默认为 None、类型正确
- [x] 1.2 Add optional `progress_func` field to `NormalizedMessage` dataclass in normalizer.py

## 2. agent_loop.run() progress_func 透传

- [x] 2.1 Write failing tests for run() progress_func: 在 tests/unit/test_agent_loop.py 新增测试，mock tool dispatch，断言 progress_func 在工具执行前被 await（仅含 name，无 args）
- [x] 2.2 Add `progress_func` parameter to `agent_loop.run()` and `_run_inner()` (default None)
- [x] 2.3 Write failing tests for progress_func exception isolation: 断言 progress_func 抛异常时 run() 不中断
- [x] 2.4 Call `progress_func({"type": "tool_call", "name": name})` in `_plan_run_slots()` before tool execution, with try/except guard
- [x] 2.5 Write failing tests for sub_agent isolation: 断言 sub_agent 内部工具调用不触发父级 progress_func
- [x] 2.6 Verify sub_agent does not receive or forward progress_func (confirm in SubAgentExecutor.run() call site)

## 3. normalizer 透传 progress_func

- [x] 3.1 Write failing tests for normalizer progress_func passthrough: mock agent_loop.run()，断言 msg.progress_func 被透传
- [x] 3.2 Pass `msg.progress_func` to `agent_loop.run()` in normalizer.route()

## 4. Slack 适配器进度反馈

- [x] 4.1 Write failing tests for Slack placeholder message: mock slack_bolt client，断言收到消息时立即 postMessage "🤔 思考中…" 并记录 ts
- [x] 4.2 Refactor `handle_message` to accept `client` (bolt injection), call `client.chat_postMessage()` for placeholder
- [x] 4.3 Write failing tests for Slack progress update with throttle: 断言 tool_call 事件触发 chat.update，1秒内重复调用被节流跳过
- [x] 4.4 Implement Slack `progress_func` closure: throttle 1s, update message with "🔧 正在调用 {tool_name}…"
- [x] 4.5 Write failing tests for Slack final reply via chat.update: 断言 reply_func 调用时更新原占位消息而非新发消息
- [x] 4.6 Implement Slack `reply_func` closure: use `client.chat_update()` with recorded `ts` to replace placeholder with final reply
- [x] 4.7 Write failing tests for Slack API failure degradation: postMessage 失败时降级静默，reply_func 仍正常执行
- [x] 4.8 Add error handling: if placeholder postMessage fails, log and fall back to original say()-based reply_func

## 5. Telegram 适配器进度反馈

- [x] 5.1 Write failing tests for Telegram typing action: mock bot，断言 progress_func 收到 tool_call 时调用 send_chat_action("typing")
- [x] 5.2 Implement Telegram `progress_func` closure in `handle_message`: call `context.bot.send_chat_action(chat_id, "typing")`
- [x] 5.3 Write failing tests for Telegram action failure isolation: send_chat_action 抛异常时不中断 run
- [x] 5.4 Add try/except guard around send_chat_action in Telegram progress_func

## 6. 收尾验证

- [x] 6.1 Run `uv run pytest tests/unit -x -q` — all new tests pass
- [x] 6.2 Run `uv run pytest tests/integration -x -q` — no regressions in im_gateway integration tests
- [x] 6.5 Run `uv run ruff format src tests && uv run ruff check src tests` — no lint errors
- [x] 6.6 Run `uv run mypy src` — type check passes
