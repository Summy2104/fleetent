## Why

主循环把消息序列直接发给 LLM（`_call_with_fallback` / `_stream_with_fallback` 的 `messages` 参数），但消息序列可能因压缩、审批占位、工具崩溃归一化、session 持久化往返等原因变得不合法：出现连续两条同角色消息、有 `tool_call` 却缺对应 `tool_result`、或有孤立 `tool_result` 找不到对应 call。OpenAI 兼容后端对这些违规会直接报 400，导致整次任务崩溃——而崩溃点离真正的成因（哪一步生成了非法序列）很远，难以排查。

AR1 终止框架在审批被拒时已手动补占位 tool_result 来保契约（`agent_loop.py` 行 238-243 的注释），AR4 上下文压缩也要求「压缩后不出现残缺 tool 记录」（agent-runtime.md 场景 10）。这些都是点对点的局部修补，缺一个**统一的消息卫生层**在发给 LLM 之前做一次契约校验与自动修复。这是 AR6。

## What Changes

- 新增**消息卫生层**（建议 `src/fleetent/message_hygiene.py`）：在每轮 LLM 调用前对消息序列做契约校验与自动修复，输出一个保证合法的序列。
- 修复**连续同角色消息**：相邻两条同角色（如连续两条 user 或两条 assistant 文本）→ 合并内容，或插入占位消息隔开，使序列角色交替合法。
- 修复**缺失 tool_result**：assistant 消息含 `tool_calls` 但后续找不到对应 `tool_call_id` 的 `tool` 消息 → 补一条「工具执行失败」占位 `tool_result`，保证每个 tool_call 都有对应 result。
- 修复**孤立 tool_result**：`tool` 消息的 `tool_call_id` 在序列中找不到对应的 assistant `tool_call` → 移除该孤立 result。
- 修复动作必须**写入运行日志（trace）**，记录做了哪些修复（类型 + 数量），便于事后定位生成非法序列的成因。
- **修复失败尽早报错**：若校验出无法安全修复的违规，MUST 在发给 LLM 之前抛出明确错误，而非把非法消息传给 LLM 触发远端 400。
- `run()` 与 `run_stream()` 在 `maybe_compress` 之后、LLM 调用之前接入卫生层，行为一致。

## Capabilities

### New Capabilities
- `message-hygiene`: 发给 LLM 的消息序列契约校验与自动修复——修复连续同角色消息、补缺失 tool_result、移除孤立 tool_result；修复动作写入 trace；无法安全修复时在调用 LLM 前尽早报错。`run()` / `run_stream()` 在每轮 LLM 调用前接入。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。审批被拒补占位、压缩保 tool 对完整的既有行为不变；消息卫生层是其上游的统一兜底，二者叠加不冲突。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/message_hygiene.py`（`sanitize()` 主入口 + 各修复规则函数 + `HygieneReport` 数据类汇总修复动作）。
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 在 `maybe_compress` 之后、`_call_with_fallback` / `_stream_with_fallback` 之前调用 `sanitize()`；将 `HygieneReport` 经 trace 记录。
  - `eval_logger.log_run` 调用补充 `hygiene_repairs` 字段（trace 写入，仅在发生修复时）。
- **配置**：无新增 Settings 字段（卫生规则为固定契约，不需部署级配置）。
- **测试**：新增 `tests/test_message_hygiene.py`；`tests/test_agent_loop.py` 补充「非法序列被修复后才发给 LLM」用例。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：终止框架、上下文压缩、permission_gate、工具 dispatch、model fallback 的既有行为；不引入新依赖。
