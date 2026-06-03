## Why

Session 清理（TTL 过期删除 + 磁盘容量驱逐）当前**只在 `save()` 写入活动时被动触发**——`save()` 调 `maybe_run_maintenance()`（session_mgr.py 行 38，带 `session_cleanup_interval_seconds` 时间门，TTL + 容量两遍 + SB2 sandbox release）。问题：**长期无 session 写入活动时清理不会发生**。一个空闲但仍在运行的服务（夜间、低峰、长会话间隙）若期间无任何 `save()`，过期 session 不会被删、磁盘容量不会被驱逐——清理被"漏触发"。需要一个**进程内的周期性触发器**，让清理按 `session_cleanup_interval_seconds` 自动跑，而不依赖是否有写入活动。

明确边界：**用进程内常驻 asyncio 任务实现，绝不引入 `cron_scheduler` / APScheduler**——这是 MCP 域 MCP3 健康探活（mcp_client.py 行 417-446）已立的先例，也是 lead 的定调（定时任务用内部机制、agent 全功能为一个原子自实现，不耦合张亮的 scheduling 域）。本 change 只新增**触发机制**，不改既有清理语义（TTL/容量/SB2 release 的"做什么"不变）。

## What Changes

- **新增进程内周期触发器**（session_mgr.py，照搬 MCP3 范式）：
  - `_session_maintenance_loop(interval)`：`while True: await asyncio.sleep(interval); maybe_run_maintenance()`，**每轮包 try/except**——单次清理异常 `logger.warning` 后**继续循环**（一次失败不杀常驻任务）。
  - `start_session_maintenance(*, interval=None)`：`interval` 缺省取 `Settings().session_cleanup_interval_seconds`；`asyncio.create_task`，存模块级 `_maintenance_task` 句柄；**幂等**（已在跑则返回现有 task，不重复建）。
  - `stop_session_maintenance()`：cancel 句柄 + `await` 并 suppress `CancelledError` + 句柄置 None；无任务时 no-op。
- **接入 server.py lifespan**：启动段 `start_session_maintenance()`（放 `start_health_monitor()` 附近）；关停段 `await stop_session_maintenance()`（放 `mcp_client.close()` / `stop_health_monitor` 关停区），不残留 task。
- **复用 `maybe_run_maintenance`**：循环只负责"按 interval 周期触发它"；既有时间门 + TTL + 容量 + SB2 release 全部复用，不重复实现。
- **CLI `run_sync` 不启常驻任务**（同 MCP3——仅 server lifespan 常驻；CLI 一次性进程，被动 `save()` 触发已足够）。

不改 `maybe_run_maintenance` / `cleanup_expired` / `enforce_capacity` / `save()`（含 SB2 release 接线）的既有逻辑；不引入新依赖；不碰 `cron_scheduler`。

## Capabilities

### New Capabilities
- `internal-session-maintenance`: session 清理的进程内周期触发——常驻 asyncio 后台循环按 `session_cleanup_interval_seconds` 周期调用既有 `maybe_run_maintenance()`（不再仅依赖 `save()` 被动触发）；启停接入 server lifespan；单次清理失败以 warning 记录后继续循环（不杀常驻任务）；start 幂等、stop 取消无残留 task；CLI 一次性进程不启常驻任务；**绝不依赖外部 cron / APScheduler**。触发任务句柄为模块级、可在测试注入/重置（同 MCP3 `_health_monitor_task` 先例）。

### Modified Capabilities
<!-- 无。本 change 纯新增"周期触发"机制，不改既有 session-ttl-cleanup / session-disk-management 的清理语义（TTL 判定、容量驱逐、SB2 release 的"做什么"均不变）。既有 spec 描述的是"清理做什么"，本 change 描述的是"何时/如何自动触发清理"，两者正交、不冲突，故以 New Capability 承载而非需求级 MODIFIED。 -->

## Impact

- **代码**：
  - `src/fleetent/session_mgr.py`：新增 `_session_maintenance_loop` / `start_session_maintenance` / `stop_session_maintenance` 三函数 + 模块级 `_maintenance_task` 句柄（仿 MCP3 `_health_monitor_loop` / `start_health_monitor` / `stop_health_monitor` / `_health_monitor_task`）。**不改** `maybe_run_maintenance` / `cleanup_expired` / `enforce_capacity` / `save()`。
  - `src/fleetent/server.py`：lifespan 启动段加 `start_session_maintenance()`、关停段加 `await stop_session_maintenance()`。
- **配置**：复用既有 `config.py` 的 `session_cleanup_interval_seconds`（行 51，默认 3600.0），loop interval 默认即取此值（与 `maybe_run_maintenance` 时间门一致）；无新增配置项。
- **测试**：扩展 `tests/test_session_mgr.py`，新增用例：循环按 interval 周期调 `maybe_run_maintenance`、一次失败不杀循环、start 幂等、stop cancel 无残留 task、CLI `run_sync` 不启常驻任务。`asyncio.sleep` mock / 注入短 interval / 用 cancel 验证停止；`SESSIONS_DIR` monkeypatch 隔离；不真实长 sleep。
- **不影响**：`save()` 被动触发路径（含 SB2 release）、TTL/容量清理语义、`session_cleanup_interval_seconds` 时间门行为、其他模块。
- **依赖与新依赖**：复用标准库 `asyncio`；**不挂 `cron_scheduler` / APScheduler**（与张亮 scheduling 域解耦，lead 定调）；不引入任何新依赖。
