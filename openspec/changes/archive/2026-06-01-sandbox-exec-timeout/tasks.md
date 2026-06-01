## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `_exec_or_cancel`（`tools.py` 行 148-166）现状：仅查外部 `cancel_token`，取消即 `exec_task.cancel()` + `destroy_workspace`（`docker rm -f`），无 `exec_timeout` 消费、无 SIGTERM 宽限
- [x] 1.2 核实 `SandboxResources.exec_timeout`（`sandbox_config.py` 行 68）已由 SB4 承载并 clamp `[1, 600]`、默认 30；本 change 仅消费随资源传入的值，不重新加载/校验
- [x] 1.3 核实 `cancellation.py` 的 `CancelToken(deadline=...)` / `is_cancelled()` 契约（合并显式 cancel 与 monotonic deadline），及 ②(sub-agent-lifecycle, AR20) 增量补全的可选 `parent` 字段（`is_cancelled()` OR `parent.is_cancelled()`，纯加法）；SB7 复用 `parent` 链接把沙箱 `exec_timeout` deadline 与外部 token 合并为单一子 token，不手写 OR
- [x] 1.4 核实 `error_classifier.py` 的 `ErrorCategory.sandbox_timeout`（行 49）与 `CLASSIFICATION_TABLE[sandbox_timeout]`（行 93，三标志均 False）已预留，本 change 经沙箱执行源接入、不改分类表结构
- [x] 1.5 核实 `SandboxClient` 既有方法均用 `asyncio.create_subprocess_exec` 调 Docker CLI（`exec` / `destroy_workspace`），新增 kill 序列方法沿用同范式

## 2. docker kill 序列封装（sandbox_client.py）

- [x] 2.1 Write failing tests for kill 序列：`kill_workspace(id)` 先发 `docker kill --signal=SIGTERM <id>`，等满固定宽限期后**无条件**发 `docker kill --signal=SIGKILL <id>`（宽限期内不轮询 `docker inspect` 探测运行态）；宽限期为可注入模块级常量（monkeypatch 极短值）。mock `asyncio.create_subprocess_exec` 捕获并断言信号序列、断言无 `docker inspect` 调用。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `kill_workspace`（SIGTERM → 固定宽限期 → 无条件 SIGKILL，宽限期内不探测）与模块级宽限期常量 `_KILL_GRACE_SECONDS=5.0`（可 monkeypatch），返回码非预期（含对已停容器 SIGKILL 的非零码）log 警告不崩，看到绿
- [x] 2.3 Write failing test for 宽限期可注入：注入极短宽限期，SIGTERM 与 SIGKILL 之间不依赖墙钟长等待。看到红
- [x] 2.4 Implement 宽限期取自模块级常量（确认 2.2 已满足）、调整使测试绿

## 3. 消费 exec_timeout 形成沙箱 deadline（tools.py）

- [x] 3.1 Write failing tests for 超时判定：`run_code`/`_exec_or_cancel` 构造 `child = CancelToken(deadline=now+exec_timeout, parent=external_token)`（`external_token` 即 `cancel_token or CancelToken()`），轮询判定为单个 `child.is_cancelled()`，执行超过 `exec_timeout` 即由该单一 token 判定超时（注入极短 `exec_timeout` + 受控慢 exec stub）。看到红
- [x] 3.2 Implement：构造带 `parent=external_token` 的 child token、轮询条件收为单个 `child.is_cancelled()`（复用 ②(AR20) 的 `parent` 链接原语合并沙箱 deadline 与外部 token，不手写 OR）；触发后按 `time.monotonic() >= child.deadline` 是否已过区分超时 / 取消；不重新加载/校验 `exec_timeout`；保持 poll + docker kill 结构不变，看到绿
- [x] 3.3 Write failing tests for 未超时路径不回归：执行在 `exec_timeout` 之内完成时正常返回 `ExecResult`，不触发强制终止（既有 run_code 用例不回归）。看到红/绿确认兼容

## 4. 超时走 docker kill 并归类 sandbox_timeout（tools.py + error_classifier 复用）

- [x] 4.1 Write failing tests for 强制终止手段：沙箱执行超时调用 `kill_workspace`（`docker kill` 序列）而非直接 `destroy_workspace`（`rm -f`）。捕获 `asyncio.create_subprocess_exec` 断言走 kill 序列。看到红
- [x] 4.2 Implement：超时分支调用 `kill_workspace`，看到绿
- [x] 4.3 Write failing tests for 归类：沙箱执行超时归类 `ErrorCategory.sandbox_timeout`，读 `CLASSIFICATION_TABLE[sandbox_timeout]` 既有标志位（三标志均 False），不新建码、不改标志位语义。看到红
- [x] 4.4 Implement：超时归一为 `sandbox_timeout`（直接读表，与 `mcp_client._disconnect_classification()` 同范式），看到绿
- [x] 4.5 Write failing tests for 返回文本与对话可继续：超时返回明确「沙箱执行超时」文本，`run_code` 正常 `return`（不抛异常杀循环）。看到红
- [x] 4.6 Implement：超时错误文本与正常返回，看到绿

## 5. 区分沙箱超时与外部取消（tools.py）

- [x] 5.1 Write failing tests for 外部取消路径：外部 `cancel_token`（经 `parent` 链接）在沙箱 deadline 之前取消，单一 `child` 触发时 `child.deadline` 未过 → 仍走 `docker kill` 序列，但归既有「已取消」语义、不归 `sandbox_timeout`、文本非「沙箱执行超时」。看到红
- [x] 5.2 Write failing tests for 沙箱超时路径：沙箱 deadline 先到，单一 `child` 触发时 `child.deadline` 已过 → 归 `sandbox_timeout`、文本「沙箱执行超时」。看到红
- [x] 5.3 Implement：触发后按 `child.deadline` 是否已过区分两路径的归类与返回文本（deadline 已过 → 超时，否则 → 取消；与 ② 的 `timed_out` vs `cancelled` 镜像，两路径共用 `kill_workspace`），看到绿

## 6. 边界与不越界核验（tasks 层断言，无新机制）

- [x] 6.1 Write failing/确认 test：非 `run_code` 工具不被施加 `exec_timeout`、不调 `docker kill`（T2 边界，本 change 不触碰 `_safe_dispatch` await 竞速）。看到红/绿确认边界
- [x] 6.2 Write failing/确认 test：超时 `docker kill` 后容器去留沿用 SB2 既有 scope 策略，本 change 不改销毁策略。看到红/绿确认边界

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
