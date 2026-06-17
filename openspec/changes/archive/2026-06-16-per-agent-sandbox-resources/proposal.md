## Why

沙箱的资源/硬化/生命周期配置（`sandbox.resources`、`sandbox.agent_scope`、`workspace_scope`/`idle_hours`、`skill_mount`）当前由 agent-runtime 模块 `integrations/sandbox` 从**机器共享**的 `platform.yaml`（`SETTINGS_PATH = paths.platform_yaml_path()`）读取。这使得 ① 无法表达"每个 agent 独享的沙箱资源/网络"——同机所有 agent 被迫共用一份；② standalone agent（只部署 agent、无 platform 服务）仍隐式依赖一个以 "platform" 命名的共享配置文件，违背 agent⊥platform 的解耦目标。

## What Changes

- agent.yaml 的 `SandboxSettings` 新增 **一份** `resources` 块（镜像 `SandboxResources` 全字段：memory/cpus/network/exec_timeout/read_only/memory_swap_mb + 硬化字段 pids_limit/tmpfs_size_mb/cap_drop_all/cap_add/no_new_privileges/init/run_as_user）与 `idle_hours`，per-agent 独享。
- **塌缩 `sandbox.agent_scope` 双档**：原 `sandbox.resources`(session 基础档) + `sandbox.agent_scope`(agent 档覆盖) 两档，收敛为**每 agent 一份资源画像**。`workspace_scope` 仍只决定数据隔离粒度，不再附带"第二档资源覆盖"。
- 配置权威改为 **agent.yaml > 代码安全默认（`SandboxResources()`）**；`integrations/sandbox` 不再为 resources/硬化/lifecycle/skill_mount 读取 `platform.yaml`。
- 接线：`init_sandbox_manager(agent)` 从 `agent.SandboxSettings.resources` 逐字段盖默认构建 `SandboxResources` + `idle_hours`，注入 `SandboxManager`（既有可注入缝）；manager 不再回落 `build_resources_by_scope()`/`load_sandbox_lifecycle()`。
- 从仓库 shipped 的 `platform.yaml` 示例/模板中**删除** `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`；提供迁移文档（搬进各 agent.yaml）。**不保留弃用告警机制**——旧 key 直接清除。
- **BREAKING**：原先依赖 `platform.yaml` 共享 `sandbox.resources`/`agent_scope` 的部署，须把这些配置搬进每个 `agent.yaml` 的 `sandbox.resources`。
- 本 change **不动** `sandbox.mode`（沙箱启用/降级轴），由后续 `per-agent-sandbox-enablement` 处理。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `sandbox-resource-limits`: 资源配置（memory/cpus/network/exec_timeout/read_only/memory_swap_mb）的来源从机器共享 `platform.yaml` 改为 **per-agent agent.yaml `sandbox.resources`**；未配字段回退代码默认（不再回落 platform.yaml）；**移除 `sandbox.agent_scope` 双档覆盖**（含 swap 的 agent_scope 跟随逻辑）。
- `sandbox-container-hardening`: 硬化字段（pids_limit/tmpfs_size_mb/cap_drop_all/cap_add/no_new_privileges/init/run_as_user）同样改为经 per-agent agent.yaml `sandbox.resources` 声明；**移除 `sandbox.agent_scope` 覆盖**（session/agent 本就同一最严加固档，塌缩后只剩一档）。

## Impact

- 代码：`src/fleetent/agent_config.py`（`SandboxSettings` 新增 `resources`/`idle_hours` 子模型）、`src/fleetent/integrations/sandbox/config.py`（resources/lifecycle/skill_mount 不再读 platform.yaml；提供从 agent 配置构建 `SandboxResources` 的入口）、`src/fleetent/integrations/sandbox/manager.py`（不回落 platform.yaml）、`src/fleetent/tools/builtin_tools.py`（`init_sandbox_manager` 注入 resources/idle_hours）。
- public API surface：agent.yaml `SandboxSettings.resources` schema；`init_sandbox_manager` 注入路径。
- owned tables：无。
- config namespace：新增 agent.yaml `sandbox.resources`/`sandbox.idle_hours`；移除 platform.yaml `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`。
- cross-module dependencies：移除 `integrations/sandbox` 对 `platform.yaml`（resources/lifecycle/skill_mount）的读取；`sandbox.mode` 读取本 change 暂留（Change 2 收口）。
- migration / shim：shipped platform.yaml 旧 key 直接删除 + 迁移文档；无 re-export、无弃用告警。
- 测试：per-agent network/resources 生效（unit 构建器 + integration manager）；standalone 无 platform.yaml 时用 agent.yaml/默认且不为 resources 读 platform.yaml；两 agent 不同 resources 互不影响；agent_scope 塌缩后单档行为正确。
