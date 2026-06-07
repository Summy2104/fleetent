## Why

P1 建立引擎 + pre_tool_use（工具前），P2 补 post_tool_use + output_transform（工具后 + 最终输出）。P3 补全消息流维度：入站用户输入（拒绝/改写/注入）、LLM 调用前（观测/注入）、LLM 回复后（改写/观测），构成完整的 request-response 链路钩子覆盖。

## What Changes

- 在 `normalizer.route` 的 `user_content` 构建后增加 `on_user_input` hook dispatch：`deny`→拒绝该消息（回 IM 用户提示）；`modified_content`→改写用户输入；`inject_context`→注入企业上下文到当次 turn。
- 在 `run_stream()` 的 user_input 处理前增加 `on_user_input` dispatch（HTTP/server 路径）：`deny`→yield error 事件；`modified_content`→替换 user_input。
- 在 `run()` 的 `sanitize` 后、`_call_with_overflow_retry` 前插入 `pre_llm_call` dispatch：`inject_context`→追加 system/user 消息到 messages；纯观测（无改写）。
- `run_stream()` 同位置（streaming token 消费前）同样插入 `pre_llm_call`。
- 在 `run()` 的 `messages.append(msg.model_dump())` 前插入 `on_assistant_reply` dispatch：`modified_content`→改写将追加进 messages 的 assistant 内容。
- `run_stream()` 的 `reply = "".join(reply_parts)` 后、break 前插入 `on_assistant_reply`：`modified_content`→替换 reply（影响后续 done 事件 + output_transform）。

## Capabilities

### New Capabilities

- `agent-hook-on-user-input`: 用户输入拦截/改写/注入钩子点
- `agent-hook-pre-llm-call`: LLM 调用前注入与观测钩子点
- `agent-hook-on-assistant-reply`: LLM 回复后改写与观测钩子点

### Modified Capabilities

（无，引擎与配置 P1 已定）

## Impact

- `src/fleetent/im_gateway/normalizer.py`：`on_user_input` dispatch（IM 路径）
- `src/fleetent/runtime/loop.py`：`on_user_input`（run_stream 入口）、`pre_llm_call`（两路 LLM 前）、`on_assistant_reply`（两路 LLM 后）
- `tests/unit/test_hook_on_user_input.py`（新建）
- `tests/unit/test_hook_pre_llm_call.py`（新建）
- `tests/unit/test_hook_on_assistant_reply.py`（新建）
