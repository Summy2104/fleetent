# memory_layer.py

## 注入侧流程

`run_sync` / `run_stream` 在开始时调 `load_memories(user_id=user_id)` → 读取最近 N 条 → 拼成 `"[Memory]\n- ..."` → 加在 system prompt 开头。

## 为什么注入到 system message 开头

system message 是"始终生效的背景指令"，LLM 被训练成把它当作整个对话的基础。放 user message 里，LLM 会误以为是本轮用户主动提供的信息，语义不对。

## 写入侧流程

run 结束后 → 把 user/assistant 对话文本喂给 haiku → 返回 JSON 数组（fact strings）→ 每条 append 到 `data/users/{user_id}/memories.jsonl`。

路径按 `user_id` 隔离，每个用户有独立的记忆文件。`data/users/` 整个目录被 `.gitignore` 排除。

## 为什么用小模型（haiku）提取记忆

提取记忆是简单任务，haiku 够用。`memory_extraction` 路由的存在就是为了省 token、省钱，同时不阻塞主回复路径（提取是 run 结束后的异步后置操作）。

## _strip_markdown_fence

LLM 有时在 JSON 外包 markdown 代码块（`` ```json ... ``` ``）：
- 第一个 `split("\n", 1)[-1]` — 去掉 `` ```json `` 首行
- 第二个 `rsplit("```", 1)[0]` — 去掉尾部 `` ``` ``

## json.loads 失败时静默 return

记忆提取是锦上添花的特性，不应阻塞主流程。失败就跳过，不影响用户拿到回复。

## _messages_to_text 跳过 system 和 tool

- system：固定的基础设施，不含用户信息
- tool：工具执行结果，是过程数据，不是用户信息

有价值的记忆来自 user 和 assistant 消息。

## load_memories 的已知缺陷

全文读取再 `splitlines()`：文件大时 O(file size)，内存风险。生产环境应改为从文件尾部反向扫描或用 `deque(maxlen=n)` 逐行读。
