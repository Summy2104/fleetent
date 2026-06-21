## Why

自进化(reflection)是交付标准 1(运行时:记忆/自进化/审批门)里**唯一仍未接线**的能力:`run_reflection` 当前只被平台 CLI(`admin_cli/maintenance.py:108`)调用,agent 运行时**从不自动跑**;而且 `apply_skill_proposal_to_boundary`(`reflection.py:616`)在 `write_skill` 后**不 reload** skill 注册表,running agent 仍用旧索引、要重启才生效。本切片把这两处接进 agent 运行时,补齐标准 1。

## What Changes

- **Part 1 · reflection 周期自动触发**(镜像已有 session-maintenance 范式):新增一个 agent-owned 进程内周期后台循环,按可配 interval **best-effort 调 `run_reflection`**(复用现有公共 API,不重写反思语义)。舱壁化:单次失败只 log,不杀循环、不改进程退出码。boot 段启动(**仅当配置 enabled**)、shutdown 段取消且无残留、启动幂等——与 `session/manager.py` 的 `_session_maintenance_loop` / `start_session_maintenance`(`agent_app.py:332` 接线)同构。
  - **仍不自动应用**:触发只是周期性**生成**提案,应用仍走既有审批(agent-owned、经 DM)——与 reflection 的「No automatic application」要求一致。
- **配置(开关 + interval 都可配)**:新增 agent 级 reflection 配置块(镜像 `scheduling: SchedulingSettings` 与 `session_cleanup_interval_seconds` 的约定),`enabled: bool = False`(**默认 OFF,per-agent opt-in**)+ `interval_seconds: float`(可配,保守默认 86400)。默认 OFF ⇒ 不开启就**零行为变化**。
- **Part 2 · apply 后 reload skill**:`apply_skill_proposal_to_boundary` 在 `write_skill` 后调 `skills.registry.reload()`,让 running agent 当场用上变更(approval 与 apply 都在 agent 侧,就地 reload)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `reflection`: 新增"agent 周期自动触发 reflection(进程内循环,config 门控、默认 OFF、可配 interval、舱壁化、boot 启停幂等;仍只生成提案不自动应用)"与"应用 skill 提案后 reload agent skill 注册表"两条要求。

## Impact

- **改动代码**:`src/fleetent/agent_config.py`(reflection 配置块);新增 reflection 周期循环模块(如 `reflection/scheduler.py`);`src/fleetent/runtime/agent_app.py`(boot 启停接线,仅 enabled 时启);`src/fleetent/reflection/reflection.py`(apply→reload)。
- **边界**:纯 **agent 侧后端**;不碰 platform、不碰 `frontend/`(与正在跑的 `add-agent-chat-console` 前端 change **零重叠**,真并行);无 schema/迁移;不破坏 agent↔platform 解耦。
- **验证基线**(无 platform 时 `agent run` 直跑)不受影响:循环默认 OFF,且 reflection 是 agent 侧能力。
- **默认行为**:默认 OFF,既有部署零变化;运维 per-agent 显式 opt-in 才启用。
- **不在本切片**:memory-maintenance 提案 auto-apply(memory 写库即生效、无内存索引、涉审批策略,单独议);post-N-turns 触发(已选周期循环)。
- **合并**:由主会话串行做(窗口只实现 + push 分支)。
