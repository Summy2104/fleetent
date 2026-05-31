## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `dispatch` 工具调用失败的归一化形态（抛异常 vs 返回错误字符串），阅读 `tool_registry.dispatch` 与 `tests/test_agent_loop.py`，据此确定 `ConsecutiveFailuresChecker` 的失败判据（落入 design Open Questions）
- [ ] 1.2 确认 `eval_logger.log_run` 签名，规划新增 `stop_reason` 参数的向后兼容方式（默认值，不破坏现有调用）
- [ ] 1.3 核对 `run()` 现状审批被拒分支（行 167-168）：确认改为终止后无下游依赖「拒绝继续」语义；确认占位 tool_result 仍需写入以保消息契约

## 2. 终止框架核心（termination.py）

- [ ] 2.1 Write failing tests for `StopReason` 枚举与 `LoopState` 数据类：`tests/test_termination.py` 断言枚举含 `normal` / `max_turns` / `consecutive_failures` / `approval_rejected` 及 3 个预留原因（`loop_detected` / `budget_exceeded` / `cancelled`）；`LoopState` 含 `turn` / `consecutive_failures` / `approval_rejected` 字段。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `StopReason`、`LoopState`，看到绿
- [ ] 2.3 Write failing tests for `TerminationController`：注册自定义 checker 后 `should_stop` 调用之、返回首个非 None 原因；无 checker 命中时返回 None。看到红
- [ ] 2.4 Implement `TerminationController`（有序 checker 列表 + register + should_stop），看到绿

## 3. 配置接入（Settings + _default_config，对齐 context_mgr 模式）

- [ ] 3.1 Write failing tests：`Settings` 含 `agent_max_turns`（默认 50）、`agent_max_consecutive_failures`（默认 3）；`termination._default_config()` 返回二者且可被覆盖（参数 > config）。看到红
- [ ] 3.2 Implement：`config.py` 的 `Settings` 增加两个字段；`termination.py` 增加 `_default_config()`（惰性 `from fleetent.config import Settings`，同 context_mgr）。看到绿

## 4. 内置 checker：max_turns

- [ ] 4.1 Write failing tests for `MaxTurnsChecker`：达到上限返回 `max_turns`，未达上限返回 None；阈值通过构造参数注入。看到红
- [ ] 4.2 Implement `MaxTurnsChecker`，看到绿

## 5. 内置 checker：consecutive_failures

- [ ] 5.1 Write failing tests for `ConsecutiveFailuresChecker`：连续失败达到阈值返回 `consecutive_failures`；一次成功重置计数为 0；阈值可注入。看到红
- [ ] 5.2 Implement `ConsecutiveFailuresChecker`，看到绿

## 6. 内置 checker：approval_rejected

- [ ] 6.1 Write failing tests for `ApprovalRejectedChecker`：`state.approval_rejected=True` 时返回 `approval_rejected`，否则返回 None。看到红
- [ ] 6.2 Implement `ApprovalRejectedChecker`（读 `state.approval_rejected` 标志），看到绿

## 7. 接入 run()

- [ ] 7.1 Write failing tests for `run()` 终止路径（mock `get_async_client_and_config` 持续返回 tool_calls）：达 max_turns 停止并返回当前回复；工具连续失败达阈值以 consecutive_failures 停止；成功调用重置失败计数；高风险工具审批被拒以 approval_rejected 停止且被拒工具仍有占位 tool_result。看到红
- [ ] 7.2 Implement：`run()` 在 `while` 顶部（`maybe_compress` 后、LLM 调用前）调用 `controller.should_stop(state)`，更新 `state.turn` / `state.consecutive_failures`；审批被拒时置 `state.approval_rejected=True` 并写占位 tool_result（替换原「继续循环」逻辑）；新增 `max_turns` / `max_consecutive_failures` 可选参数（None 经 `_default_config()` 回落 Settings）。看到绿

## 8. 接入 run_stream()

- [ ] 8.1 Write failing tests for `run_stream()` 终止路径：max_turns 与 consecutive_failures 在流式路径同样生效、行为与 run() 一致（approval_rejected 因流式不做审批拦截而不适用）。看到红
- [ ] 8.2 Implement：`run_stream()` 接入同一 `TerminationController` 与 `LoopState` 更新逻辑（仅 max_turns / consecutive_failures）。看到绿

## 9. trace 写入终止原因码

- [ ] 9.1 Write failing tests：强制终止时 `log_run` 收到对应 `stop_reason`；正常结束（finish_reason != tool_calls）记 `StopReason.normal`。看到红（先验证 log_run 尚未接收 stop_reason）
- [ ] 9.2 Implement：为 `log_run` 增加 `stop_reason` 参数（默认 normal，向后兼容），`run()` / `run_stream()` 在终止/正常结束时传入实际原因。看到绿

## 10. 收尾

- [ ] 10.1 运行全量 `uv run pytest -q` 确认全绿，无回归
- [ ] 10.2 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 全部通过
- [ ] 10.3 确认 `loop_detected` / `budget_exceeded` / `cancelled` 仅作为枚举值存在、无对应 checker 注册（预留扩展点不误触发）
