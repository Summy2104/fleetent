## Why

`fleetent agent run <name>`（standalone 与 platform spawn 走的同一条路径）启动时，skill 索引扫描被指向 per-agent 的 `home_dir/skills`，但 sandbox 的 skills 挂载在 `skill_mount.source` 未配时回退到全局 `<base>/skills`。两个根发散：agent 在 `<available_skills>` 里看得到、`read_skill` 也读得到 per-agent skill（如 `common-ns-system-query`），但 `run_code` 在容器 `/workspace/skills` 下找不到它的脚本，导致「能看到 skill、却无法执行其脚本」。这违反了 `sandbox-skill-mount` 既有的「可用 skill 的资源在 `$SKILLS_DIR` 下必须可达」契约。

## What Changes

- `boot` 计算一次 per-agent skills 根（`home_dir/skills`，即当前喂给 skill scan 的同一个值），并将其作为 skills 挂载源的默认值向下传递至 `init_sandbox_manager`，使**挂载根与扫描根同源**。
- `init_sandbox_manager` 在 agent 的 `sandbox.skill_mount.source` 未显式配置（None）时，使用该 per-agent skills 根作为 `SkillMountConfig.source` 默认，取代当前 `effective_skill_root(None)` 回退到全局 `<base>/skills` 的错误行为。
- 优先级保持不变：agent.yaml 显式 `skill_mount.source` 仍然优先；未配置时落到 per-agent `home_dir/skills`；`skill_mount.enabled=false` 仍然不挂载。
- `materialize_builtin_skills` 同样作用于该有效根（builtin 资源仍在挂载根下可达）。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `sandbox-skill-mount`: 收紧/明确「单一有效根」要求——挂载的有效根 MUST 与当前 agent 的 skill 索引扫描根一致（agent-run 模式下为 per-agent `home_dir/skills`），保证 `<available_skills>` 中列出的任一 skill 的脚本/资源在容器 `$SKILLS_DIR` 下可达；`skill_mount.source` 显式配置时仍优先。

## Impact

- **owning package**: `runtime`（`runtime/agent_app.py` 的 `boot`/`_start_infra` 接线）+ `tools`（`tools/builtin_tools.py` 的 `init_sandbox_manager`）。
- **public API surface**: `init_sandbox_manager` 新增一个可选的 per-agent skills 根入参（默认 None 保持向后兼容）；不改变其它对外签名。
- **owned tables**: 无。
- **config namespace**: 无新增；沿用既有 `sandbox.skill_mount.{enabled,read_only,source}`。
- **cross-module dependencies**: 仅 runtime→tools 既有方向；不触碰 `platform` 方向（agent runtime MUST NOT import platform 的契约不受影响）。
- **migration / shim plan**: 无数据/路径迁移；纯行为修复 + 入参扩展，旧调用（不传新参）退化为当前全局回退行为，不破坏现有测试。
