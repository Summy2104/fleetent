## Context

`runtime/agent_app.py` 的 `boot` 在 line 389 用 `scan_skills(skills_dir=str(home_dir / "skills"))` 把 skill 索引扫描显式钉在 per-agent home（`home_dir = resolve_home(agent_id)` = `<base>/agents/<name>`），注释明确「self-contained: never the process CWD or FLEETENT_SKILLS_DIR」。

但 sandbox 挂载走另一条解析：`init_sandbox_manager(agent)`（`tools/builtin_tools.py`，由 `_start_infra` 调用）从 `agent.sandbox.skill_mount` 构造 `SkillMountConfig(source=sm.source)`，`SandboxManager._resolve_skill_mount` 再调 `skill_registry.effective_skill_root(cfg.source)`。当 `source` 为 None 时，`effective_skill_root(None)` → `_resolve_skills_dir(None)` → `FLEETENT_SKILLS_DIR or paths.base_dir()/skills` = 全局 `<base>/skills`。

`paths.base_dir()`（`<base>` = FLEETENT_HOME）与 per-agent home（`<base>/agents/<name>`）不同，于是扫描根与挂载根发散：agent 索引/`read_skill` 看到 per-agent skill，但 `run_code` 在容器 `/workspace/skills`（挂的是全局根）下找不到其脚本。platform 与 standalone 因为都 spawn `fleetent agent run`（`platform/agent_lifecycle/controller.py`），共用这条路径，故同一处修复同时覆盖两者。

## Goals / Non-Goals

**Goals:**
- 挂载根与扫描根同源：agent-run 下 `skill_mount.source` 未配时默认采用 per-agent `home_dir/skills`。
- 单一来源：`boot` 只计算一次 per-agent skills 根，scan 与 mount 默认消费同一个值，结构上杜绝再次发散。
- 保持优先级与兼容：显式 `skill_mount.source` 优先；`enabled=false` 仍不挂；不传新参的旧调用退化为当前行为。

**Non-Goals:**
- 不改 `effective_skill_root` / `_resolve_skills_dir` 的全局默认语义（其它非 agent-run 入口不在本次范围）。
- 不引入新配置项、不改 `agent.yaml` schema、不动 platform 方向依赖。
- 不改 builtin 物化、ro/rw、config_hash、is_blocked_mount 等既有挂载语义。

## Decisions

**决策 1：在 `boot` 计算 per-agent skills 根并向下传递，而非让 manager 自行感知 home。**
`init_sandbox_manager` / `SandboxManager` 是 agent-runtime 通用组件，不应内建「per-agent home 解析」知识。`boot` 是唯一已知 `home_dir` 的地方，且已为 scan 算出 `home_dir/"skills"`。把这同一个值作为「skills 挂载源默认」入参向下穿过 `_start_infra → init_sandbox_manager`，是最小且语义清晰的接线。
- 备选：让 `SandboxManager` 调 `resolve_home`——被否，会让通用 sandbox 组件耦合 agent-home 布局。
- 备选：把 `effective_skill_root(None)` 的全局默认直接改成 per-agent——被否，`effective_skill_root` 是无 home 上下文的通用函数，改它会波及其它调用方。

**决策 2：默认仅在 `skill_mount.source` 为 None 时生效，显式 source 优先。**
`init_sandbox_manager` 现已读 `agent.sandbox.skill_mount.source`；新增的 per-agent 默认只在该值为 None 时填入，保持「显式配置 > per-agent 默认 > （兜底）全局」优先级，不破坏既有可配置性。

**决策 3：`init_sandbox_manager` 新增可选入参（默认 None）承载 per-agent skills 根。**
默认 None 时退化为当前 `effective_skill_root(None)` 全局行为，所有现有调用与测试不传新参即保持原状；只有 `boot` 路径传入该值，行为被修正。

## Risks / Trade-offs

- [materialize 目标随之变为 per-agent 根] → 预期内：builtin（如 getting-started）会物化进 per-agent `home_dir/skills`，与挂载根一致，`$SKILLS_DIR` 下仍可达；幂等且不覆盖同名用户 skill。
- [config_hash 因挂载源路径变化而触发既有容器重建] → 升级后首次创建会因 source 由全局变 per-agent 而 hash 失配重建一次，符合 spec 既有「挂载源变更触发重建」语义，一次性、无数据损失。
- [非 agent-run 的其它入口仍走全局默认] → 本次只修 `boot`；若未来出现新的 agent 启动入口，需同样传入 per-agent 根（已在 Non-Goals 标注，靠 TDD 测试钉住 boot 路径行为）。

## Migration Plan

纯行为修复 + 入参扩展，无 schema/数据/路径迁移。部署后已运行的 my-bot 重启即生效；回滚为还原代码改动，无残留状态。
