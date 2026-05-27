# agent_loop.py

## 三个入口

| 函数 | 用途 |
|------|------|
| `run(messages, ...)` | 异步，接收完整消息列表，返回文本 |
| `run_sync(user_input, ...)` | 同步包装，CLI 使用；内部调 `asyncio.run(run(...))` |
| `run_stream(user_input, ...)` | 异步生成器，返回 SSE 事件字典流 |

## 核心循环结构（run）

```
while True:
    messages = maybe_compress(messages)       # token 超限时压缩历史
    response = await LLM(messages + tools)
    messages.append(response.message)
    if finish_reason != "tool_calls": break
    for each tool_call: dispatch → append role:"tool" result
```

## run_sync 与 run 的职责划分

`run_sync` 负责会话初始化：扫描 skills、加载记忆、注入 system prompt、构建初始 messages 列表。`run` 本身只处理循环，不知道记忆和 skills 的存在——职责分离，测试更容易 mock。

`run_stream` 是自包含的，直接做初始化（因为它是 HTTP 路径的主入口），所以它自己调 `load_memories` 和 `match_skill`。

## is_sub_agent 过滤

```python
schemas = [s for s in get_schemas() if s["function"]["name"] != "sub_agent"] \
    if is_sub_agent else get_schemas()
```

子 agent 运行时 `is_sub_agent=True`，`sub_agent` 工具从 schema 列表中剔除。LLM 看不到这个工具，因此无法调用，阻断了递归嵌套。

## streaming 时 tool_calls 的累积

LLM 流式输出时，一个工具调用的 `name` 和 `arguments` 分散在多个 chunk 的 delta 里，需要按 `tc.index` 累积再拼接：

```python
tool_calls_acc: dict[int, dict[str, str]] = {}
# 每个 chunk：
tool_calls_acc[idx]["name"] += tc.function.name or ""
tool_calls_acc[idx]["arguments"] += tc.function.arguments or ""
```

非流式 `run()` 中，整条 assistant 消息一次返回，不需要累积。

## finish_reason 处理

- `"tool_calls"` — 继续循环，dispatch 工具结果
- 其余所有值（`"stop"`、`"length"`、`"content_filter"`）— 统一 break

`"length"` 时返回截断内容，不做特殊处理。

## messages.append(msg) 直接追加 SDK 对象

OpenAI SDK 接受 `ChatCompletionMessage` 对象放进 messages 列表并自动序列化。流式路径需要手动构造 dict（因为没有完整的 ChatCompletionMessage 对象），非流式路径可以直接 append SDK 对象。

## type: ignore[arg-type]

`get_schemas()` 返回 `list[dict[str, Any]]`，SDK 期望 `Iterable[ChatCompletionToolParam]`。运行时兼容，mypy 不认，用 `# type: ignore[arg-type]` 跳过。
