## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 AR1 框架接口：`termination.py` 的 `TerminationChecker` Protocol、`TerminationController.register` / `should_stop`、`StopReason.cancelled` 已存在，确认本 change 仅新增 `CancellationChecker` + 透传 token
- [x] 1.2 核实主循环检查点：`run()`（行 290）与 `run_stream()`（行 487）每轮开头 `controller.should_stop(state)`，确认取消能在「下一次 LLM 调用前」被捕获
- [x] 1.3 核实工具调度链：`_safe_dispatch`（行 62）→ `tool_registry.dispatch`（行 61）的签名与调用点，确认 token 透传的注入位置
- [x] 1.4 核实 `SandboxClient.exec` / `destroy_workspace`（sandbox_client.py 行 46-72）与 `run_code`（tools.py 行 50-71）的容器生命周期，确认 `ws_id` 局部于 `run_code`（`SandboxClient` 实例不持有），据此确认 D3b 的 run_code 编排硬中止落点与 `destroy_workspace` 幂等性
- [x] 1.5 核实 `_build_schema`（tool_registry.py 行 84-101）遍历 `inspect.signature` 生成 `properties` / `required` 的逻辑，确认按 D3 选定的「带外注入」判据排除 token 参数的改法；确认 `dispatch` 对 opt-in 工具显式追加 `cancel_token` kwarg、不接受 token 的存量工具签名与 schema 不变

## 2. CancelToken 原语（cancellation.py，对外契约）

- [x] 2.1 Write failing tests：`tests/test_cancellation.py` 断言默认 `CancelToken()` 永不取消（`is_cancelled()` 恒 False）；`cancel()` 后 `is_cancelled()` 为 True 且幂等。看到红
- [x] 2.2 Implement `CancelToken` 标志 + `cancel()` + `is_cancelled()`，看到绿
- [x] 2.3 Write failing tests：携带 `deadline`（单调时钟）的 token 在未到点时 `is_cancelled()` 为 False、超过 deadline 后为 True；显式 `cancel()` 与 deadline 任一满足均视为已取消。看到红
- [x] 2.4 Implement deadline 合并进 `is_cancelled()`（单调时钟），看到绿

## 3. CancellationChecker（接入 AR1 框架）

- [x] 3.1 Write failing tests：`CancellationChecker(token)` 在 `token.is_cancelled()` 时 `check()` 返回 `StopReason.cancelled`，否则 None。看到红
- [x] 3.2 Implement `CancellationChecker`，看到绿

## 4. 主循环接入 token（agent_loop.py）

- [x] 4.1 Write failing tests for `run()`：传入已取消的 token → 主循环在下一检查点以 `cancelled` 终止、不再调 LLM、`log_run(stop_reason=cancelled)`；不传 token（默认）时行为与现状字节级一致。mock `get_async_client_and_config`。看到红
- [x] 4.2 Implement `run()`：新增 `cancel_token` 参数（None → 默认永不取消 token）；`_build_controller` 注册 `CancellationChecker`；token 透传 `_safe_dispatch`。看到绿
- [x] 4.3 Write failing tests for `run_stream()`：同等取消行为；取消后正常走收尾出口、不泄漏半截事件。看到红
- [x] 4.4 Implement `run_stream()` 接入，看到绿

## 5. token 流入工具调度与 schema 排除（tool_registry.py）

- [x] 5.1 Write failing tests：`dispatch` 对声明接受 token 的工具以带外 kwarg 注入 token；对未声明的工具调用签名不变、行为不变。看到红
- [x] 5.2 Implement `dispatch` 的 token 带外透传（按 D3 选定的注册标记/参数名约定），看到绿
- [x] 5.3 Write failing test for `_build_schema` 排除 token 参数：声明接受 token 的工具，其生成的 schema `properties` 与 `required` 均**不含** token 参数（防止被当作 string 必填字段暴露给 LLM）；未声明 token 的工具 schema 不变。看到红
- [x] 5.4 Implement `_build_schema`（行 84-101）跳过带外注入参数，看到绿

## 6. 沙箱硬中止（tools.py run_code 编排 + sandbox_client.py 幂等销毁）

- [x] 6.1 Write failing tests for `destroy_workspace` 幂等：`tests/test_sandbox_client.py` mock docker 子进程，断言对同一 `ws_id` 二次 `destroy_workspace`（容器已不存在 / `rm -f` 已执行）不抛异常。看到红
- [x] 6.2 Implement `SandboxClient.destroy_workspace` 幂等（容器不存在时 `rm -f` 不报错），看到绿
- [x] 6.3 Write failing tests for `run_code` 取消编排：mock `SandboxClient`，断言 `run_code` 接受带外 `cancel_token`，token 取消时由 `run_code` 调 `destroy_workspace(ws_id)` 强制销毁并中止 `exec` 等待（不无限等待）、返回取消结果；正常路径不销毁中途容器、行为不变；`finally` 兜底销毁不重复抛。看到红
- [x] 6.4 Implement `run_code` 的 asyncio 编排（`exec` 任务 + token 观察任务，取消调 `destroy_workspace(ws_id)`），看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误模式
