# sub_agent.py

## 职责

让主 agent 把多个独立任务并行委托给子 agent 执行，收集结果后统一返回。

## 并发执行

```python
coros = [self._run_one(task, ...) for task in tasks]
return list(await asyncio.gather(*coros))
```

`asyncio.gather` 并发运行所有任务，总耗时约等于最慢那个任务，而不是所有任务之和。

## 最大嵌套深度为 1

子 agent 调用 `agent_loop.run(..., is_sub_agent=True)`，agent_loop 会把 `sub_agent` 工具从 schema 中剔除。LLM 看不到这个工具，因此子 agent 无法再派生子 agent。

这是有意的约束——递归嵌套会让 token 用量和延迟难以预测。

## 部分失败不整体失败

```python
except Exception as exc:
    return SubAgentResult(name=name, result=None, error=str(exc), ...)
```

`_run_one` 捕获所有异常并封装进 `SubAgentResult.error`，不向 `asyncio.gather` 传播。`gather` 会等所有任务完成（包括失败的），调用方拿到完整结果列表，自行决定如何处理失败项。

## 为什么不用 return_exceptions=True

`asyncio.gather(return_exceptions=True)` 会把异常对象混在结果里，类型不统一。用统一的 `SubAgentResult` 结构让调用方的处理代码更简单（检查 `r.error is None` 即可）。

## 子 agent 没有独立的 session

子 agent 共享 `parent_user_id`，但没有 session_id——它们是无状态的单次 run，用完即弃，不写入会话历史。`parent_session_id` 只是附在结果上，供调用方追踪来源，不用于 session 存储。
