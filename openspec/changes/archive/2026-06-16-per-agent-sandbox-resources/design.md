## Context

`integrations/sandbox/config.py` 用 `SETTINGS_PATH = paths.platform_yaml_path()` 从 `platform.yaml` 读取：
`load_sandbox_resources` / `build_resources_by_scope`（session 基础档 + `sandbox.agent_scope` 覆盖 agent 档）、
`load_sandbox_lifecycle`（`workspace_scope`/`idle_hours`）、`load_skill_mount_config`（`skill_mount`）。
`manager.SandboxManager.__post_init__`（manager.py:195）在 `resources_by_scope` / `skill_mount` 为 None 时回落调用上述 loader。
接线缝 `init_sandbox_manager(agent)`（tools/builtin_tools.py:69）已持 `AgentFile` 并从 `agent.SandboxSettings`
取 skill_mount/image_persistence/setup_command/multi_user/workspace_scope 构建 manager，**唯独未注入 `resources_by_scope`**，
故资源/硬化仍走 platform.yaml。agent.yaml 的 `SandboxSettings`（agent_config.py:290）`extra="forbid"`，当前无 `resources` 字段。

## Goals / Non-Goals

**Goals:**
- 每个 agent 在 `agent.yaml` 独享一份沙箱资源/硬化/lifecycle 配置。
- `integrations/sandbox` 不再为 resources/硬化/lifecycle/skill_mount 读取 `platform.yaml`。
- standalone agent 无 `platform.yaml` 也能完整解析沙箱配置。
- 复用既有 `init_sandbox_manager(agent)` 注入缝；塌缩 `agent_scope` 双档为单档。

**Non-Goals:**
- 不动 `sandbox.mode`（启用/降级轴）——属 `per-agent-sandbox-enablement`（Change 2）。
- 不改 backend 选型（已 agent.yaml 优先）、不改容器创建的 flag 语义、不改 `workspace_scope` 的数据隔离语义。
- 不改资源/硬化字段的安全默认值。

## Decisions

1. **agent.yaml schema**：`agent_config.py` 给 `SandboxSettings` 加 `resources: SandboxResourcesSettings`（pydantic 子模型，镜像 `SandboxResources` 全字段，各字段 Optional/带默认）与 `idle_hours: float`。`extra="forbid"` 保持——字段显式声明后即可被接受。
2. **单档塌缩**：删除 `sandbox.agent_scope` 概念。每 agent 一份 `resources`，session/agent `workspace_scope` 共用同一份资源画像（数据隔离粒度仍由 workspace_scope 决定）。`build_resources_by_scope` 的"两档"语义退化为"两 scope 同档"。
3. **构建入口**：在 `integrations/sandbox/config.py` 增 `resources_from_agent_settings(agent_sandbox) -> SandboxResources`（逐字段把 agent 配置盖在 `SandboxResources()` 默认上 + 既有校验/clamp/枚举回退复用）。`init_sandbox_manager` 调它构建 `SandboxResources`，连同 `idle_hours` 一并注入 `SandboxManager(resources_by_scope={SESSION: r, AGENT: r}, idle_hours=...)`。
4. **停读 platform.yaml**：manager 既然总被注入 `resources_by_scope`/`skill_mount`/lifecycle，删除 `__post_init__` 对 platform.yaml loader 的回落；`config.py` 移除/弃用 `load_sandbox_resources`/`build_resources_by_scope`/`load_sandbox_lifecycle`/`load_skill_mount_config` 中读 platform.yaml 的路径（`SETTINGS_PATH` 仅 `mode` 仍用，留待 Change 2）。
5. **shipped platform.yaml 清理**：从仓库 `config/*.example`/模板删除 `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`；docs 写迁移说明。不加弃用告警。
6. **校验复用**：字段级 clamp（exec_timeout [1,600]）、枚举回退（network）、非正数回退（memory/cpus/pids/tmpfs）等既有逻辑迁入 `resources_from_agent_settings`，保证非法值仍记录+回退、不静默接受。

## Risks / Trade-offs

- **BREAKING**：依赖 platform.yaml 共享 `sandbox.resources`/`agent_scope` 的部署需逐 agent 搬配置——迁移文档承载；本机单 agent（用户场景）几乎无感。
- **测试面广**：现有大量 unit/integration 直接调 `load_sandbox_resources`/`build_resources_by_scope`/写临时 platform.yaml 验证资源。需同步改为"经 agent.SandboxSettings.resources 构建"路径；保留字段级校验用例。属预期工作量，以 TDD 锁定。
- **manager 注入恒满**：注入后 `resources_by_scope` 永不为 None，`__post_init__` 回落分支删除后须确保所有构造点（含测试 fixture）都注入或走新默认构造，避免 None 解引用。
- **agent_scope 删除的兼容**：仍有测试/代码引用 `sandbox.agent_scope`——需清理并在 spec 中明确移除（已在 delta 反映）。
- 与 Change 2 的边界：本 change 保留 `mode` 的 platform.yaml 读取（`enablement.py`），故"沙箱零读 platform.yaml"的最终护栏放在 Change 2 收口，本 change 的护栏仅断言"资源/lifecycle/skill_mount 解析不读 platform.yaml"。
