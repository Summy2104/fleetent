## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `dispatch` 失败形态：混合（unknown tool 返回字符串、PermissionError/工具异常抛出）；`run()` 当前对 dispatch 无 try/except（工具异常会崩溃 run）。判据定为：**失败 = dispatch 抛异常**（循环捕获后计数+写错误 tool_result），返回字符串=成功
- [x] 1.2 确认 `log_run` 签名：`(user_input, reply, messages, elapsed_s, usage=None, model_used=None, user_id=None, agent_name=None)`；新增末位 kw 参数 `stop_reason: str | None = None` 即向后兼容
- [x] 1.3 核对 `run()` 审批被拒分支（agent_loop.py 行 167-168）：被拒后造字符串当 tool_result 继续循环，无下游依赖此语义；改为置标志+写占位 tool_result+下轮终止

## 2. 终止框架核心（termination.py）

- [x] 2.1 Write failing tests for `StopReason` 枚举与 `LoopState` 数据类：`tests/test_termination.py` 断言枚举含 `normal` / `max_turns` / `consecutive_failures` / `approval_rejected` 及 3 个预留原因（`loop_detected` / `budget_exceeded` / `cancelled`）；`LoopState` 含 `turn` / `consecutive_failures` / `approval_rejected` 字段。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `StopReason`、`LoopState`，看到绿
- [x] 2.3 Write failing tests for `TerminationController`：注册自定义 checker 后 `should_stop` 调用之、返回首个非 None 原因；无 checker 命中时返回 None。看到红
- [x] 2.4 Implement `TerminationController`（有序 checker 列表 + register + should_stop），看到绿

## 3. 配置接入（Settings + _default_config，对齐 context_mgr 模式）

- [x] 3.1 Write failing tests：`Settings` 含 `agent_max_turns`（默认 50）、`agent_max_consecutive_failures`（默认 3）；`termination._default_config()` 返回二者且可被覆盖（参数 > config）。看到红
- [x] 3.2 Implement：`config.py` 的 `Settings` 增加两个字段；`termination.py` 增加 `_default_config()`（惰性 `from fleetent.config import Settings`，同 context_mgr）+ `resolve_limits()` 纯解析函数。看到绿

## 4. 内置 checker：max_turns

- [x] 4.1 Write failing tests for `MaxTurnsChecker`：达到上限返回 `max_turns`，未达上限返回 None；阈值通过构造参数注入。看到红
- [x] 4.2 Implement `MaxTurnsChecker`，看到绿

## 5. 内置 checker：consecutive_failures

- [x] 5.1 Write failing tests for `ConsecutiveFailuresChecker`：连续失败达到阈值返回 `consecutive_failures`；阈值可注入。看到红（计数累计/重置语义由 run() 集成测试覆盖，见 7.x）
- [x] 5.2 Implement `ConsecutiveFailuresChecker`，看到绿

## 6. 内置 checker：approval_rejected

- [x] 6.1 Write failing tests for `ApprovalRejectedChecker`：`state.approval_rejected=True` 时返回 `approval_rejected`，否则返回 None。看到红
- [x] 6.2 Implement `ApprovalRejectedChecker`（读 `state.approval_rejected` 标志），看到绿

## 7. 接入 run()

- [x] 7.1 Write failing tests for `run()` 终止路径（mock `get_async_client_and_config` 持续返回 tool_calls）：达 max_turns 停止并返回当前回复；工具连续失败达阈值以 consecutive_failures 停止；成功调用重置失败计数；高风险工具审批被拒以 approval_rejected 停止且被拒工具仍有占位 tool_result。看到红
- [x] 7.2 Implement：`run()` 终止检查点在 `while` 顶部（`maybe_compress` 前）调用 `controller.should_stop(state)`；`state.turn` 每次 LLM 调用后自增；`_safe_dispatch` 捕获工具异常归一化为失败并累计/重置 `consecutive_failures`；审批被拒置 `approval_rejected=True` + 占位 tool_result；新增 `max_turns` / `max_consecutive_failures` 参数经 `resolve_limits` 回落 Settings。看到绿

## 8. 接入 run_stream()

- [x] 8.1 Write failing tests for `run_stream()` 终止路径：max_turns 与 consecutive_failures 在流式路径同样生效、行为与 run() 一致（approval_rejected 因流式不做审批拦截而不适用）。看到红
- [x] 8.2 Implement：`run_stream()` 接入同一 `TerminationController`（include_approval=False）与 `LoopState`；dispatch 改用 `_safe_dispatch` 追踪 consecutive_failures。看到绿

## 9. trace 写入终止原因码

- [x] 9.1 Write failing tests：强制终止时 `log_run` 收到对应 `stop_reason`；正常结束（finish_reason != tool_calls）记 `StopReason.normal`。看到红（先验证 log_run 尚未接收 stop_reason）
- [x] 9.2 Implement：`log_run` 增加 `stop_reason: str | None = None`（默认 None 向后兼容，非 None 写入 entry），`run()` / `run_stream()` 在终止/正常结束时传入实际原因。看到绿

## 10. 收尾

- [x] 10.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）384 passed，无回归（不带 key 时 20 个 webhook 测试因 `Settings` 缺 key 失败，属环境，非本次引入）
- [x] 10.2 我的文件 ruff format/check 全绿；mypy：termination.py 唯一错误（`Settings()` call-arg）与 context_mgr 既有模式一致，agent_loop.py 错误均为 base 既有（且经 `_safe_dispatch` 合并由 8 减至 6），**未新增任何 mypy 错误模式**（项目 base 即有 66 个遗留）
- [x] 10.3 加回归守卫 `test_build_controller_never_yields_reserved_reasons`：`loop_detected` / `budget_exceeded` / `cancelled` 无 checker，即便 state 全置位也只触发 3 个生效原因
