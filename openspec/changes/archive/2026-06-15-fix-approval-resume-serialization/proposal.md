## Why

审批批准后**恢复（resume）整体失效**：`approve <id>` 文本命令或按钮决定后，续跑抛 `TypeError: Object of type ToolContext is not JSON serializable`，导致工具虽已执行、但会话保存/续跑崩溃，用户拿不到任何结果。

根因：`runtime/approval_resume._execute_tool` 以 **dict** 形式把 `entry["tool_args"]` 传给 `registry.dispatch(tool_name, tool_args, tool_context=...)`。`dispatch` 在 args 为 dict 时直接复用同一引用（`kwargs = arguments_json`），随后把 `tool_context`（及 `cancel_token`）**原地注入该 dict**。`_execute_tool` 的 `finally` 再对这个**被污染的 `tool_args`** 调 `build_tool_args_summary` → `json.dumps` 撞上 `ToolContext` 崩溃。正常 loop 路径传的是 JSON **字符串**（`json.loads` 每次产新 dict），不会回污染调用方，故只有 resume 命中。这也违反了 trace-tool-spans 的既有不变量「trace 记录失败 MUST 仅记 warning、MUST NOT 影响 run 继续」。

## What Changes

- **根因修复**：`registry.dispatch` MUST NOT 原地改调用方传入的 args 映射——args 为 dict 时**复制后再注入** out-of-band 的 `tool_context`/`cancel_token`，使注入只进入本次调用的 kwargs、绝不回写调用方的 dict。
- **纵深防御**：`observability.build_tool_args_summary` 用 `json.dumps(..., default=str)`，任何不可序列化的入参值都降级为字符串而非抛异常——保证 args_summary 永不使 trace 记录（及其调用者）崩溃。
- 二者叠加使审批恢复在「续跑里再次触发受门控工具」等复杂路径下也稳健；out-of-band 注入的上下文也不会出现在持久化的 args_summary 里（摘要只反映模型入参）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `trace-tool-spans`: `tool_call` 事件的 args_summary 构建 MUST 纳入 best-effort 容错（含恢复 run），失败仅记 warning、不中断 run；out-of-band 注入的 `tool_context`/`cancel_token` MUST NOT 进入 args_summary，且工具分发 MUST NOT 因注入而改写调用方的 args 映射。

## Impact

- `src/fleetent/tools/registry.py`：`dispatch` 复制 dict args（不原地改）。
- `src/fleetent/observability/traces.py`：`build_tool_args_summary` 加 `default=str`。
- 测试：dispatch 不污染调用方 dict 单测；build_tool_args_summary 容不可序列化值单测；resume 执行受门控工具后 args_summary/保存不崩的回归单测。
- 无数据迁移、无 config 变更、无 owned table 变更；不改审批触发面/风险分级；修复独立于 #265（接收方展示/回执）。
