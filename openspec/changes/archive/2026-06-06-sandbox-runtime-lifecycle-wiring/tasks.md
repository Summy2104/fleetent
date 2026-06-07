## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `_start_infra`（`runtime/agent_app.py`）现状：`get_effective_mode()` 一次探测、MCP 注册、`session_mgr.start_session_maintenance()`；确认接线插入点
- [x] 1.2 核实 `SandboxManager.sweep_idle` / `cleanup_orphans` / `SandboxClient` 签名与 `builtin_tools._get_manager()` 进程单例；核实 `session_mgr` 维护循环测试写法与 `check_test_layers` 对「mock 管理器的后台 sweep 循环」单测的判定（如被判 integration 再迁移）

## 2. sandbox 维护循环模块（integrations/sandbox/maintenance.py）

- [x] 2.1 Write failing tests（`tests/unit/test_sandbox_maintenance.py`）：`start_idle_sweep` 创建 task；幂等（二次返回同一 task）；循环按小 interval 调用 `_get_manager().sweep_idle()`；单次 `sweep_idle` 抛错不终止循环（下次间隔仍调用）；`stop_idle_sweep` 取消且无残留。`patch` `builtin_tools._get_manager` 为 mock。运行 `uv run pytest tests/unit/test_sandbox_maintenance.py -x -q` 看红
- [x] 2.2 Implement `maintenance.py`（镜像 `session_mgr` 模式：模块级 `_sweep_task`、`_idle_sweep_loop` 每迭代故障隔离、幂等 `start_idle_sweep`、`stop_idle_sweep`；循环体内惰性 `from fleetent.tools.builtin_tools import _get_manager`），看绿

## 3. 公共 API 导出（integrations/sandbox/__init__.py）

- [x] 3.1 Write failing test：`from fleetent.integrations.sandbox import start_idle_sweep, stop_idle_sweep` 可用。看红
- [x] 3.2 Implement `__init__` 导出 + `__all__`，看绿

## 4. _start_infra 接线（runtime/agent_app.py）

- [x] 4.1 Write failing tests：`mode != OFF` 时 `_start_infra` 调用 `cleanup_orphans` 一次 + `start_idle_sweep`；`mode == OFF`（Docker 不可用）时二者都不调用；`cleanup_orphans` 抛错时记录警告且不阻断后续启动（仍走到 `start_session_maintenance`）。`patch` `get_effective_mode` / `cleanup_orphans` / `start_idle_sweep` / MCP / session。看红
- [x] 4.2 Implement `_start_infra` 接线（取 `get_effective_mode()` 返回值；`mode != OFF` 才 best-effort `cleanup_orphans(SandboxClient())` + `start_idle_sweep()`），看绿

## 5. 文档

- [x] 5.1 更新 `docs/capabilities/sandbox-improvements.md` 的 Change 2 段：从「计划」改为已实现，补决策（裸 asyncio 循环 / 惰性管理器 / Docker 门控 / 固定间隔）与取舍
- [x] 5.2 更新 `docs/capabilities/sandbox.md`：孤儿清理由「实现就绪、待接线」更新为「agent 运行时启动已接线」；闲置回收注明已周期调度

## 6. 收尾

- [x] 6.1 `uv run pytest tests/unit/test_sandbox_maintenance.py tests/unit/test_agent_run_cli.py -x -q` 绿（及其他受影响 agent_app 单测）
- [x] 6.2 `uv run pytest tests/unit -q` 无新增失败（既有 4 path 族失败除外）
- [x] 6.3 `uv run ruff format src tests && uv run ruff check`（本 change 文件全绿）
- [x] 6.4 `uv run mypy`（本 change 新增/修改文件无问题）
- [x] 6.5 `uv run python scripts/check_test_layers.py`（本 change 新增测试无违规）
