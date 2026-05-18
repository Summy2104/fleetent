# Context Management Design

## 和记忆层的区别

| | context_mgr.py | memory_layer.py |
|--|----------------|-----------------|
| 解决什么 | 当前对话放不进 token 上限 | 下次对话记得上次发生的事 |
| 触发时机 | 会话中途，token 超阈值 | 会话结束时 |
| 输出 | 摘要消息，注回 messages 列表 | 事实条目，存 JSONL |
| 生命周期 | 会话内 | 跨会话 |

两者独立，不合并：触发时机不同，失败影响级别不同（压缩失败是高优先级问题，记忆提取失败是可静默跳过的非关键路径）。

## 触发机制

监控每次 LLM 调用前的 messages 总 token 数。超过可配置阈值时触发压缩。

```python
# 配置示例
CONTEXT_CONFIG = {
    "max_tokens": 200_000,      # 模型上限
    "compress_threshold": 0.8,  # 达到 80% 时触发
    "keep_recent": 10,          # 压缩后保留最近 N 条
}
```

阈值设为 80% 而非 100%：给摘要生成和下一轮回复留出空间。

## 压缩策略

压缩时保留：
- system prompt（始终保留）
- 最近 `keep_recent` 条消息（原文保留）
- 所有未完成的 tool_call/tool_result 对（丢掉会导致 LLM 报错）

压缩掉：
- 更早的历史消息

压缩后的消息列表结构：

```
[system prompt]
[summary message]   ← 用 haiku 生成，替换掉旧历史
[最近 10 条原文]
```

summary message 的 role 用 `"user"` + 特殊前缀，或单独的 `"system"` 追加：

```json
{
  "role": "system",
  "content": "[Earlier conversation summary]\n用户目标是 X。已完成：Y、Z。当前状态：..."
}
```

## token 计数

用字符数粗估（1 token ≈ 4 字符），避免引入 tiktoken 依赖。精度够用，不影响触发逻辑。

```python
def estimate_tokens(messages: list[Any]) -> int:
    total = sum(len(str(m)) for m in messages)
    return total // 4
```

## 模块接口

```python
def maybe_compress(
    messages: list[Any],
    config: ContextConfig = DEFAULT_CONFIG,
) -> list[Any]:
    """If messages exceed threshold, compress and return new list. Otherwise return as-is."""
```

在 agent_loop.py 的 while 循环开头调用，每轮 LLM 调用前检查一次。

## 和 user_id 的关系

context_mgr 是无状态的纯函数（输入 messages，输出 messages），不感知 user_id。user_id scoping 由 agent_loop 和 memory_layer 负责，不渗透进来。
