## Why

`agent_loop.py` 的 `run()` 与 `run_stream()` 当前是 `while True` 无限循环，唯一的退出条件是 LLM 返回 `finish_reason != "tool_calls"`。一旦模型持续请求工具（或工具持续失败），循环无法自行终止，没有步数上限、没有连续失败保护，也没有统一的「为何停止」记录。这是 v1.0 运行治理的地基缺口——后续的预算管控、循环检测、取消传播都需要一个统一的终止出口才能接入。

## What Changes

- 新增**终止框架**：在主循环引入单一终止检查点，每轮 LLM 调用前后统一判断「是否应停止、停止原因是什么」。
- 引入**可扩展的终止策略注册表**（extension seam）：每个终止原因是一个独立的 checker，注册到框架；新增原因只需新建 checker 文件并注册，无需修改 `agent_loop.py` 热点。
- 本次接入三个**无需新增基础设施**的终止原因：
  - `max_turns`：主循环迭代次数达到上限。
  - `consecutive_failures`：工具调用连续失败达到阈值。
  - `approval_rejected`：高风险工具被人工拒绝（复用 `run()` 中已存在的 permission_gate 流程）——纠正现状缺陷：当前审批被拒后被当作工具结果继续循环，与 agent-runtime.md 场景 4「reject 后取消当次任务」相悖。
- `max_turns` 与连续失败阈值**支持部署级配置**：在 `config.py` 的 `Settings` 增加 env 字段（沿用 `context_*` / `permission_gate_*` 既有模式），并支持 `run()`/`run_stream()` 调用参数覆盖。
- 终止时将**终止原因码写入运行日志（trace）**，供统计「任务为何失败」与生成面向用户的提示。
- 为 `loop_detected` / `budget_exceeded` / `cancelled` 预留注册扩展点（本次**不实现**具体判定逻辑）。
- `run()` 与 `run_stream()` 共用同一套终止框架，行为一致。
  - 注意：`run_stream()` 现状**不做审批拦截**（直接 dispatch），故 `approval_rejected` 当前仅在 `run()` 路径生效；补齐流式审批不属本次范围。

## Capabilities

### New Capabilities
- `agent-loop-termination`: agent 主循环的终止条件管理——统一终止检查点、可扩展终止策略注册表、终止原因码写入 trace；本次覆盖 `max_turns`、`consecutive_failures`、`approval_rejected` 三类原因。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。permission_gate 自身行为不变；审批被拒后的「继续 vs 终止」收口在新 capability agent-loop-termination 内处理。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/termination.py`（`TerminationController` + 策略注册表 + `StopReason` 枚举 + 内置 checker）。
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 的 `while True` 接入终止检查点；终止时记录原因码；`run()` 审批被拒改为置终止标志（不再当作工具结果继续循环）。
  - `eval_logger.log_run` 调用补充 `stop_reason` 字段（trace 写入）。
- **配置**：`config.py` 的 `Settings` 增加 `agent_max_turns: int = 50`、`agent_max_consecutive_failures: int = 3`（env 可配，沿用 `context_*` 模式）；`termination.py` 经 `_default_config()` 惰性读取（同 `context_mgr._default_config()`），调用参数 > Settings > 字段默认值三层优先级；测试通过传参/config 注入隔离，不实例化真 `Settings`。
- **测试**：新增 `tests/test_termination.py`；`tests/test_agent_loop.py` 补充终止路径用例。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：model fallback、工具 dispatch、permission_gate 自身、上下文压缩的既有行为；不引入新依赖。
