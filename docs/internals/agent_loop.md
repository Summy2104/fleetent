# agent_loop.py

## 核心循环结构

```
while True:
    response = LLM(messages + tools)
    messages.append(response.message)      # SDK 接受对象，内部自动序列化
    if finish_reason != "tool_calls": break
    for each tool_call: dispatch → append role:"tool" result
```

## finish_reason 的可能值

- `"tool_calls"` — 继续循环
- `"stop"` — 正常结束
- `"length"` — 触发 max_tokens，返回截断内容
- `"content_filter"` — 内容被过滤

当前循环对所有非 `"tool_calls"` 的情况统一 break，包括 `"length"`。

## 多工具调用时的 messages 顺序

LLM 返回一条带多个 tool_calls 的 assistant 消息，之后必须为每个 tool_call_id 各追加一条 `role:"tool"` 消息，全部追加完才能发下一次 LLM 请求。API 会校验 tool_call_id 的对应关系，缺少任何一条会报错。

## messages.append(msg) 为什么不用 .model_dump()

OpenAI SDK 接受 ChatCompletionMessage 对象直接放进 messages 列表，内部自动序列化。`msg.model_dump()` 效果等价，SDK 帮你省了这一步。

## type: ignore[arg-type]

`get_schemas()` 返回 `list[dict[str, Any]]`，SDK 期望 `Iterable[ChatCompletionToolParam]`。运行时兼容，mypy 不认，用 `# type: ignore[arg-type]` 跳过检查。
