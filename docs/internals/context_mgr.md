# context_mgr.py

## 职责

当会话消息历史的 token 数接近上限时，用小模型把旧消息压缩成摘要，保留最近几轮和完整的 system prompt。

## 触发条件

```python
threshold = int(max_tokens * compress_threshold)   # 默认 200_000 * 0.8 = 160_000
if estimate_tokens(messages) <= threshold:
    return messages   # 直接返回原列表，同一对象
```

未触发时返回同一对象（`result is messages`），不复制，零开销。

## 压缩流程

1. 分离 system 消息和对话消息
2. 从对话尾部取 `keep_recent` 条作为 tail（调 `_keep_tail` 确保不截断 tool 对等）
3. 把 tail 之前的消息喂给 haiku 生成摘要
4. 返回 `[system_msgs..., summary_msg, tail...]`

## _keep_tail 的 identity check

```python
while tail and _role(tail[0]) == "tool":
    idx = next((i for i, m in enumerate(msgs) if m is tail[0]), 0)
    #                                              ^^
    #                              identity (is), not equality (==)
```

必须用 `is`，不能用 `==`。消息是 dict，两条内容完全相同的 tool 结果 `==` 为 True，用 `==` 会匹配到错误位置，把错误的 assistant 消息带进 tail。

## _summarize 的异常处理

```python
except Exception:
    return "[Earlier conversation summary unavailable]"
```

摘要生成失败时返回占位文本，不抛异常。循环继续，LLM 收到的是降级摘要而不是崩溃。

## token 估算精度

`estimate_tokens = total_chars // 4`，是粗略估算（实际 1 token ≈ 4 chars for English，中文更少）。精确计数需要 tiktoken，但粗估对于触发阈值判断已经足够——提前几百 token 触发压缩没有负面影响。
