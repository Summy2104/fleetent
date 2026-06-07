## Context

P1（agent-hook-engine）已建立 `runtime/hooks.py`（HookContext/HookResult/dispatch/has_hooks/reset）及 `hooks_enabled`/`hooks_decision_failure`/`hooks_timeout_seconds` 配置。本 change 在此基础上追加两个变换类钩子点：工具调用后（post_tool_use）和最终输出前（output_transform）。

## Goals / Non-Goals

**Goals:** post_tool_use（结果脱敏/重写/审计）+ output_transform（回复变换/审计），复用 P1 引擎，零新配置字段。

**Non-Goals:** P3–P4 的其它钩子点；决策类能力（post_tool_use/output_transform 均为纯变换+观测，不支持 decision）。

## Decisions

### D1：post_tool_use 落在 backfill，改写结果进 messages

`_backfill_slots` 改为 `async def`（使内部可 `await dispatch`）。调用方 `run()` 处的 `_backfill_slots(...)` 改为 `await _backfill_slots(...)`。`run_stream` 内联 backfill 已在 async context，直接内联 dispatch。

触发条件：`governance.hooks_enabled and hooks.has_hooks("post_tool_use")`（双门，零开销）。payload：`{tool_name, tool_args, tool_result, failed}`。仅对**实际执行的工具**（非 pre_tool_use deny 产生的 placeholder）触发——placeholder 表示工具未执行，无真实结果可变换。`modified_content` 替换进 messages 的 `content`（截断前）；已产出 SSE `tool_result` 事件的 run_stream 不可撤回（设计如此，文档化）。

### D2：output_transform 落在 reply 定稿后、返回/yield 前

`run()` 有两处 `return reply`（1469 early-exit + 1661 正常），`run_stream()` 有两处 `yield done`（1838 early-exit + 2149 正常）。四处均插 dispatch，封装为内联 helper（避免重复）：

```python
async def _apply_output_transform(reply: str, governance, session_id, agent_name, user_id) -> str:
    if governance is not None and governance.hooks_enabled and hooks.has_hooks("output_transform"):
        hres = await hooks.dispatch(...)
        if hres.modified_content is not None:
            return hres.modified_content
    return reply
```

`run_stream` 的 `yield done` 先 await transform，再 yield，content 已改写。

### D3：变换点不支持 decision，strict 无意义

post_tool_use 和 output_transform 是变换类（无 veto 能力）；`dispatch` 的 `strict` 参数传 `False`（保持 fail-open）；hook 失败记 warn + 跳过，不改流程。与 P1 引擎实现一致，无需新增配置。

## Risks / Trade-offs

- **run_stream tool_result SSE 已发出**：post_tool_use 改写只影响进 messages 的副本，不影响已流出的 SSE 事件。这是设计权衡（流式不可回撤），文档化即可。
- **_backfill_slots 改 async**：调用方只有一处（run() 主循环），改动小、风险低；run_stream 已内联故无调用方变化。
