## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `session_mgr.maybe_run_maintenance`（行 38）签名/语义：带 `session_cleanup_interval_seconds` 时间门、TTL + 容量两遍、返回移除 session_ids；确认本 change 只周期调它、不改它
- [x] 1.2 核实 `save()`（行 ~275）的被动触发路径与 SB2 `_release_sandboxes` 接线——确认本 change 不动该路径
- [x] 1.3 核实 MCP3 范式（mcp_client.py 行 417-446）：`_health_monitor_loop` / `start_health_monitor`（幂等）/ `stop_health_monitor`（cancel + suppress + 置 None）/ 模块级 `_health_monitor_task`（行 49），照搬到 session_mgr
- [x] 1.4 核实 server.py lifespan 启停接入点（`start_health_monitor()` 行 127、关停区 `mcp_client.close()` 行 149）与 CLI `run_sync`（agent_loop.py 行 1166）——确认 lifespan 启停、CLI 不启常驻

## 2. 周期触发循环 + 幂等启停（session_mgr.py，照搬 MCP3）

- [x] 2.1 Write failing tests：`start_session_maintenance(interval=极短)` 返回运行中 task；`stop_session_maintenance()` cancel 后 `task.done()` 且模块级 `_maintenance_task is None`（无残留）；无任务时 stop 为 no-op 不抛异常。运行 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 看到红
- [x] 2.2 Implement `_session_maintenance_loop` / `start_session_maintenance` / `stop_session_maintenance` + 模块级 `_maintenance_task`（仿 MCP3：create_task、suppress CancelledError、句柄置 None），看到绿
- [x] 2.3 Write failing test 幂等：`_maintenance_task` 已在跑时再次 `start_session_maintenance` 返回**现有** task、不建第二个。看到红
- [x] 2.4 Implement 幂等守卫（`_maintenance_task is not None and not done()` 则返回现有 task），看到绿

## 3. 循环周期调 maybe_run_maintenance + 失败不杀循环

- [x] 3.1 Write failing test：循环按注入短 interval 周期调用 `maybe_run_maintenance`（mock `maybe_run_maintenance` 计数 / mock `asyncio.sleep` 驱动），无活动期也触发。看到红
- [x] 3.2 Implement 循环 `while True: await asyncio.sleep(interval); maybe_run_maintenance()`（interval 缺省取 `Settings().session_cleanup_interval_seconds`），看到绿
- [x] 3.3 Write failing test 失败不杀循环：mock `maybe_run_maintenance` 首轮抛异常、后续正常 → 断言异常被 `logger.warning` 记录、循环未退出、下一轮仍调 `maybe_run_maintenance`。看到红
- [x] 3.4 Implement 每轮 try/except：catch → `logger.warning` → continue（不吞异常=warning 记录；不 re-raise 以免杀任务），看到绿

## 4. lifespan 启停接入 + CLI 不常驻

- [x] 4.1 Write failing test：CLI 一次性路径（`run_sync`）执行后 `session_mgr._maintenance_task is None`（CLI 不启常驻）。看到红
- [x] 4.2 Implement server.py lifespan：启动段加 `session_mgr.start_session_maintenance()`（`start_health_monitor()` 附近）、关停段加 `await session_mgr.stop_session_maintenance()`（`mcp_client.close()` / `stop_health_monitor` 关停区）；CLI `run_sync` 不加。看到绿（CLI 用例转绿）

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`，无回归（既有 save()/maintenance/SB2 release 用例不破，≥1414+新增）
- [x] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿（只动本 change 文件）
- [x] 5.3 `uv run mypy src` 无新增错误模式
- [x] 5.4 `docs/capabilities/wave2-apply-decisions.md` 末尾追加 `## [follow-up] internal-session-maintenance` 决策节
