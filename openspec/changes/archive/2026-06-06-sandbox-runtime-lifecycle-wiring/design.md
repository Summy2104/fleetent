## Context

`runtime/agent_app._start_infra` 是单机 agent 运行时的「best-effort 进程基础设施」启动点，目前做：Docker 探测（`get_effective_mode`）、per-agent MCP 注册、`session_mgr.start_session_maintenance()`。它**没有**调用 `cleanup_orphans`，也没有调度 `SandboxManager.sweep_idle`——二者均有实现+spec+测试，仅缺运行时接线（platform/runtime 拆分遗留）。

`session_mgr` 已确立后台维护模式：模块级 `_maintenance_task`、`_session_maintenance_loop(interval)`（`while True: await asyncio.sleep(interval); ...`）、幂等 `start_session_maintenance()`、`stop_session_maintenance()`，**刻意不走 cron_scheduler/APScheduler**（与 user-level 调度器解耦，沿用 MCP 健康监控先例）。进程级 `SandboxManager` 是 `builtin_tools._get_manager()` 的惰性单例。

## Goals / Non-Goals

**Goals:**
- 让 agent 运行时启动时清理上次遗留的孤儿沙箱容器（满足 `sandbox-orphan-cleanup` 在拆分后架构中的启动意图）。
- 让 agent-scope 闲置回收真正周期运行（使 `idle_hours` 生效、触发 commit-then-destroy 固化依赖流程）。
- 复用既有 best-effort + 裸 asyncio 后台循环模式，零新依赖。

**Non-Goals:**
- 不改 `cleanup_orphans` / `sweep_idle` 自身行为（仅接线）。
- 不改 session-scope 释放（仍由 `session_mgr` 维护循环负责）。
- 不支持多实例共享同一 Docker daemon（沿用 orphan-cleanup 的「单实例独占 daemon」前提）。

## Decisions

**D1：裸 asyncio 后台循环，镜像 `session_mgr.start_session_maintenance`，不走 cron_scheduler。** 与 session 维护一致、与 user-level 调度器解耦。新模块 `integrations/sandbox/maintenance.py` 持模块级 `_sweep_task`、幂等 `start_idle_sweep`、`stop_idle_sweep`、每迭代 try/except 故障隔离。替代方案：注册到 cron_scheduler——被否，cron_scheduler 是 user-level 定时任务设施，进程内维护不应耦合它（既有先例）。

**D2：循环内惰性取 `_get_manager()`，不在启动期或模块顶层持管理器引用。** `integrations/sandbox/maintenance.py` 顶层 import `builtin_tools` 会形成循环（builtin_tools → integrations.sandbox）；故在循环体内 `from fleetent.tools.builtin_tools import _get_manager` 惰性 import（与 `session_mgr` 在函数内 `from fleetent import agent_config` 一致）。好处：① 不强制启动期建管理器；② sweep 始终作用于 run_code 所用的同一进程单例；③ 空 registry 时 sweep 为 no-op，session scope 下天然无害。

**D3：复用启动期那一次 Docker 探测结果做门控。** `_start_infra` 已 `await get_effective_mode()`（一次探测、进程缓存）；本 change 取其返回值，`mode != OFF`（即 Docker 可用）才执行清理 + 启动 sweep。不新增第二次探测（与 orphan-cleanup spec「探测协调：一次探测」一致）。

**D4：清理 best-effort，失败不阻断启动。** `try: await cleanup_orphans(SandboxClient()) except Exception: _logger.warn(...)`，与 `_start_infra` 既有 MCP 注册的 best-effort 姿态一致。`cleanup_orphans` 本身已对 Docker 不可用返回 0、不抛；D3 的门控是额外的「可用才清理」短路。

**D5：sweep 间隔取固定默认值（`_DEFAULT_SWEEP_INTERVAL_SECONDS = 1800`，30min），可注入。** 不从 `idle_hours` 推导——按固定间隔扫描，闲置容器在 `idle_hours + 间隔` 内被回收，足够及时；固定值更简单、测试可注入小 interval。

**D6：新建 capability `sandbox-runtime-lifecycle-wiring`，不 MODIFY 既有 spec。** 「运行时如何接线/调度」是与「清理能力本身」「闲置回收行为本身」并列的独立关注点。本 change 在拆分后的 agent 运行时架构中*实现*了 `sandbox-orphan-cleanup` 既有的启动清理意图——在 proposal 中点明二者关系，避免 MODIFY/RENAME 既有需求标题带来的 delta 复杂度。

## Risks / Trade-offs

- **[sweep 循环持有过期管理器引用]** → 每迭代惰性 `_get_manager()` 取进程单例，永不持旧引用。
- **[启动期被迫早建管理器]** → 惰性 import + 惰性取管理器规避；首次 sweep tick 才可能触发建管理器，空 registry 下 no-op。
- **[多实例共享 Docker daemon 下启动全删误伤同伴]** → 沿用 orphan-cleanup「单实例独占 daemon」前提，HA 多实例列为未来工作。
- **[后台任务在进程退出时悬挂]** → 提供 `stop_idle_sweep`；进程退出本身也会回收 task（与 `session_mgr._maintenance_task` 一致，后者亦不强制在 drain 中 stop）。

## Migration Plan

纯加性接线，无数据迁移。升级后 agent 运行时启动即生效（Docker 可用时）。回退：移除 `_start_infra` 中的两行接线即恢复旧行为。
