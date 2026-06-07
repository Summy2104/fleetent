## Context

P1/P2 已建立引擎、pre_tool_use、post_tool_use、output_transform。本 change 补全消息流的三个钩子点：用户输入入站（on_user_input）、LLM 调用前（pre_llm_call）、LLM 回复后（on_assistant_reply）。涉及两个模块：`normalizer.py`（IM 路径的 on_user_input）和 `loop.py`（其余所有点）。无新配置字段，复用 P1 引擎契约。

## Goals / Non-Goals

**Goals:** on_user_input（IM + run_stream 入口）+ pre_llm_call（loop turn 顶）+ on_assistant_reply（LLM 响应后）。

**Non-Goals:** P4 生命周期钩子点；改写 run() 直接接受 messages 列表的路径上的 on_user_input（无单一 user_input 字符串可钩）。

## Decisions

### D1：on_user_input 两处落点

**IM 路径 (normalizer.route)**：`user_content = await _build_user_content(msg)` 之后、`history.append({"role": "user", "content": user_content})` 之前。dispatch 结果：`deny`→向 IM 用户回复拒绝提示并 return；`modified_content`→替换 `user_content`；`inject_context`→在 `user_content` 后追加一条 system/user 消息（通过给 history 插入实现）。

**server/HTTP 路径 (run_stream)**：`user_input` 字符串是函数参数，在 `_build_user_content`/`build_message_with_images` 构建前 dispatch（fallback：对 `user_input: str` 直接 dispatch）：`deny`→yield `{"type": "error", "content": deny_reason}` 并 return；`modified_content`→替换 `user_input`；`inject_context`→注入（通过 messages 前追加）。

### D2：pre_llm_call 在 sanitize 之后、LLM call 之前

**run()** 的 `_call_with_overflow_retry` 前（line ~1530）：dispatch `pre_llm_call`，payload `{message_count: len(messages)}`（不暴露 messages 内容，避免大对象序列化）；`inject_context`→在 messages 末尾追加 `{"role": "user", "content": inject_context}`（LLM 下一 turn 将看到）。纯观测返回 None 无副作用。`run_stream()` 同位置（streaming 第一个 token 前）。

### D3：on_assistant_reply 在 assistant 消息进 messages 前

**run()**：`msg = choice.message` 之后、`messages.append(msg.model_dump())` 之前。`modified_content`→新建 model_dump dict 并把 content 字段替换。仅对 `content not None`（有文本）的 turn 触发；tool_calls turn（content=None）跳过，因为没有 assistant 文本可改写。

**run_stream()**：final text reply 的 `reply = "".join(reply_parts)` 之后、`break` 之前。`modified_content`→替换 `reply`（后续 output_transform + done 事件均用改写后的值）。已流出的 text_delta 不可撤回（设计如此，文档化）。

### D4：inject_context 追加语义

`inject_context` 在 pre_llm_call 追加为 `{"role": "user", "content": inject_context}`（符合 OpenAI messages contract）；在 on_user_input 追加为额外消息（紧随用户消息之后）。不修改原 history（注入仅影响本次 turn 发给 LLM 的 messages 副本）——wait，实际上 messages 是共享列表，需在发完这轮 LLM 后清理注入，或只在 messages 的本轮视图上注入。设计简化：**仅用于观测场景**，inject_context 写入 messages 并在 session history 中持久化（与其他 injection 行为一致）。运维方应注意注入会进历史。

## Risks / Trade-offs

- on_user_input IM 路径需要 normalizer import hooks，需注意 agent/platform 解耦：normalizer 已有 `import fleetent.platform.*` 存量，但 hooks 是 agent-local，只要不引入新的 platform import 即合规。
- run_stream on_user_input `deny`：yield error 后 run_stream 早退，caller 不应继续消费事件流。
- pre_llm_call 的 inject_context 追加进 messages 会进 session history，运维方需注意。
