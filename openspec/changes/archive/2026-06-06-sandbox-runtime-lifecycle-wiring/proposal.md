## Why

`cleanup_orphans`（孤儿容器清理）与 `SandboxManager.sweep_idle`（agent-scope 闲置回收）都有实现、归档 spec、通过的单测，但在 platform/runtime 拆分后（`server.py` 不再跑 sandbox，agent 执行移入 `fleetent agent run` → `runtime/agent_app`），**二者在 agent 运行时启动路径 `_start_infra` 中都没有调用点**：

- `cleanup_orphans` 从未在运行时启动时被调用——`sandbox-orphan-cleanup` spec 要求「启动时自动触发一次孤儿清理」，但实现未满足（spec-实现漂移）。后果：一次 `fleetent agent run` 崩溃遗留的 `sandbox-*` 容器跨重启泄漏。
- `sweep_idle` 从未被调度——`session_mgr` 的维护循环只释放 **session-scope** 容器（`_release_sandboxes`），**agent-scope** 闲置回收无任何周期触发。后果：`agent` scope 容器永不回收、`idle_hours` 配置形同虚设、commit-then-destroy 固化依赖的流程从不触发。

本 change 把这两条接入 agent 运行时启动，复用 `session_mgr.start_session_maintenance` 已确立的「裸 asyncio 后台循环（不走 cron_scheduler/APScheduler）」模式。

## What Changes

- 新增 `src/fleetent/integrations/sandbox/maintenance.py`：`start_idle_sweep` / `stop_idle_sweep` + `_idle_sweep_loop`，周期性调用进程级 `SandboxManager.sweep_idle`。镜像 `session_mgr` 的维护循环：模块级可重置 task、幂等启动、每次迭代故障隔离（单次失败记录后继续，不杀死常驻循环）。循环内**惰性**取进程管理器（`builtin_tools._get_manager()`），避免循环 import 与启动期强制建管理器。
- 在 `runtime/agent_app._start_infra` 接线：复用启动期那次 Docker 探测的结果（`get_effective_mode()`），**Docker 可用（mode != OFF）时**才：① 调用一次 `cleanup_orphans(SandboxClient())`（best-effort，失败记录不阻断启动）；② `start_idle_sweep()` 启动周期回收。Docker 不可用时二者都不执行（与 orphan-cleanup spec「可用才清理」一致）。
- sandbox 包 `__init__` 导出 `start_idle_sweep` / `stop_idle_sweep`。

## Capabilities

### New Capabilities
- `sandbox-runtime-lifecycle-wiring`: Agent 运行时（`fleetent agent run`）启动时 SHALL 在 Docker 可用的前提下清理一次孤儿沙箱容器，并启动一个周期性后台任务回收闲置的 agent-scope 沙箱；清理与回收均为 best-effort，任一失败 MUST NOT 阻断运行时启动；Docker 不可用时二者都不执行。

### Modified Capabilities
<!-- 不以 MODIFIED 表达。`sandbox-orphan-cleanup` 的「启动时自动清理」与 `sandbox-lifecycle` 的「闲置回收行为」需求本身不变；
     本 change 新增的是「agent 运行时如何把它们接线/调度起来」这一独立关注点，落在新 capability 下以 ADDED 表达。
     说明：本 change 在拆分后的 agent 运行时架构中*实现*了 sandbox-orphan-cleanup 既有的「启动时清理」意图。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/integrations/sandbox/maintenance.py`（后台 sweep 循环）。
  - 修改 `src/fleetent/runtime/agent_app.py` `_start_infra`：Docker 可用时接入 `cleanup_orphans` + `start_idle_sweep`。
  - 修改 `src/fleetent/integrations/sandbox/__init__.py`：导出新接口。
- **测试**：新增 `tests/unit/test_sandbox_maintenance.py`（start 幂等 / 循环调用 sweep_idle / 故障隔离 / stop 取消，mock 管理器、小 interval）；扩充 agent_app 启动接线测试（mode != OFF 时调 cleanup_orphans + start_idle_sweep；OFF 时都不调）。docker / asyncio.sleep 全 mock 或小 interval。
- **不影响**：`run_code` 工具契约、session 维护（session-scope 释放仍由 `session_mgr` 负责）、resolver、permission_gate；不引入新依赖。
