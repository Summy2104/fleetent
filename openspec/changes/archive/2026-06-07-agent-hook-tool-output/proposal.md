## Why

P1 建立了 hook 引擎 + pre_tool_use（工具调用前拦截/改参），P2 补全"工具调用后"与"最终输出前"两个变换点，使运维方可在工具结果和 agent 最终回复上做脱敏/重写/审计，而无需改内核。

## What Changes

- 在 `_backfill_slots`（`run()` 路径）和 `run_stream` 内联 backfill 中增加 `post_tool_use` hook dispatch：工具返回后、内容追加进 messages 前触发；`modified_content` 替换工具结果。
- 在 `run()` 的两处 `return reply` 前增加 `output_transform` hook dispatch：最终回复定稿后、返回前触发；`modified_content` 替换 reply。
- 在 `run_stream()` 的两处 `yield {"type": "done", ...}` 前同样增加 `output_transform`。
- `_backfill_slots` 由 `def` 改为 `async def`（使内部可 await dispatch；调用方 `run()` 改为 `await _backfill_slots(...)`）。
- 两个钩子点复用 P1 已定死的接口契约（HookContext/HookResult/dispatch）；无需新增 agent.yaml 配置字段。

## Capabilities

### New Capabilities

- `agent-hook-post-tool-use`: 工具调用后结果变换与观测钩子点
- `agent-hook-output-transform`: agent 最终回复输出变换与观测钩子点

### Modified Capabilities

（无，引擎与配置在 P1 已定，本批仅增集成点）

## Impact

- `src/fleetent/runtime/loop.py`：`_backfill_slots` 改 async；两路 backfill + 两处 `return reply` + 两处 `yield done` 增加 dispatch
- `tests/unit/test_hook_post_tool_use.py`（新建）
- `tests/unit/test_hook_output_transform.py`（新建）
