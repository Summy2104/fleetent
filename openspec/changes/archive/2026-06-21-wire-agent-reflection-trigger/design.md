## Context

`run_reflection`(reflection 公共 API)只被平台 CLI(`admin_cli/maintenance.py:108`)调,agent 运行时从不自动跑。agent 侧已有现成范式可镜像:`session/manager.py` 的 `_session_maintenance_loop(interval)` + `start_session_maintenance`/`stop_session_maintenance`(进程内周期后台循环,舱壁化,`agent_app.py:332` boot 接线,`internal-session-maintenance` spec 规范)。`apply_skill_proposal_to_boundary`(`reflection.py:616`)`write_skill` 后不 reload;`skills/registry.py` 已有 `reload()`。

## Goals / Non-Goals

**Goals:** agent 能按可配周期自动跑 reflection 生成提案(默认 OFF、opt-in、可配 interval、舱壁化、boot 启停幂等);apply skill 提案后就地 reload 让变更当场生效;补齐标准 1。
**Non-Goals:** 不自动应用提案(仍走审批);不做 post-N-turns 触发;不做 memory 提案 auto-apply;不碰 platform/前端;无 schema。

## Decisions

**D1 · 周期后台循环,镜像 session-maintenance,而非耦合进热路径。**
新增 `reflection/scheduler.py`:`_reflection_loop(agent_id, interval)`(`while True: sleep(interval); best-effort run_reflection`)+ `start_reflection_scheduler()`/`stop_reflection_scheduler()`。与 `_session_maintenance_loop` 同构:模块级单 task 句柄、启动幂等(已运行则返回现有 task)、停止取消且无残留。**不**用 CronScheduler(那是 task/IM 投递导向,语义不符)。备选 post-N-turns 钩子——否决(耦合热路径)。

**D2 · 舱壁化 + best-effort。** 单次 `run_reflection` 失败只 log(`reflection_cycle_failed`),循环继续,不改进程退出码、不影响其它组件——遵循异步资源/关停舱壁化原则。

**D3 · 配置:开关与 interval 都可配,默认 OFF。** 新增 agent 级 reflection 配置块(镜像 `scheduling: SchedulingSettings`):`enabled: bool = False` + `interval_seconds: float = 86400.0`。boot 时 **仅当 `reflection.enabled`** 才 `start_reflection_scheduler(interval=...)`;否则完全不起循环(零行为变化)。interval 从配置读(类比 `start_session_maintenance` 读 `session_cleanup_interval_seconds`)。

**D4 · owner-task 启停接线。** 在 `agent_app` boot 段(`start_session_maintenance` 附近)按 enabled 启动;在 shutdown/drain 段 `stop_reflection_scheduler()` 取消,谁起谁关(同 task 亲和),取消后无残留。

**D5 · apply 后就地 reload(Part 2)。** `apply_skill_proposal_to_boundary` 在 `write_skill` 成功后调 `skills.registry.reload()`(复用既有 hot-reload 的原子切换语义,不重写)。这不违反「No automatic application」:apply 本就发生在审批之后;reload 只是让已批准的变更当场生效。

## Risks / Trade-offs

- **[误读为破坏"No automatic application"]** → 触发只**生成**提案、应用仍需审批;Part 2 的 reload 发生在审批后的 apply 路径。spec 文案显式声明,测试守"触发不写 skills 文件"。
- **[reflection 跑 LLM/花 token]** → 默认 OFF + per-agent opt-in + 可配 interval;运维显式开启并定节奏才花费。
- **[循环异常拖垮 agent]** → 舱壁化:单次失败只 log、循环存活、不动退出码;测试覆盖"一次抛错后下次仍触发"。
- **[reload 失败]** → 复用 registry.reload() 既有"失败保留旧索引并告警"语义,不自造。
- **[与 (3) 前端并行]** → 纯 agent 后端,零文件重叠;合并由主会话串行做。
