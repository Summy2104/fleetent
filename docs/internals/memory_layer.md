# memory_layer.py

## 写入侧流程

run 结束后 → 把 user/assistant 对话文本喂给 haiku → 返回 JSON 数组（fact strings）→ 每条 append 到 data/memories.jsonl。

## 为什么用小模型（haiku）

提取记忆是简单任务，haiku 够用。这就是 `memory_extraction` 路由存在的原因——省 token，省钱。

## _strip_markdown_fence

LLM 有时在 JSON 外包 markdown 代码块（```json ... ```）。
- 第一个 split("\n", 1)[-1] — 去掉 ```json 首行
- 第二个 rsplit("```", 1)[0] — 去掉尾部 ```

## json.loads 失败时静默 return

记忆提取是锦上添花的特性，不应阻塞主流程。失败就跳过，不影响用户拿到回复。

## _messages_to_text 跳过 system 和 tool

- system：固定的基础设施，不含用户信息
- tool：工具执行结果，是过程数据，不是用户信息

有价值的记忆来自 user 和 assistant 消息。
