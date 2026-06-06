## ADDED Requirements

### Requirement: Agent 运行时启动时清理孤儿沙箱容器

Agent 运行时（`fleetent agent run` → `_start_infra`）启动时 SHALL 在 Docker 可用的前提下调用一次孤儿沙箱清理（`cleanup_orphans`），回收上次异常退出遗留的 `sandbox-*` 容器。清理为 best-effort：失败（含 Docker 不可用、清理抛错）MUST 记录警告且 MUST NOT 阻断运行时启动。Docker 不可用时 SHALL NOT 触发清理。

#### Scenario: Docker 可用时启动触发一次清理
- **WHEN** agent 运行时启动且 Docker 可用（有效 mode 非 off）
- **THEN** 孤儿清理被调用一次

#### Scenario: Docker 不可用时不触发清理
- **WHEN** agent 运行时启动且 Docker 不可用（有效 mode 为 off）
- **THEN** 不调用孤儿清理，运行时仍正常完成启动

#### Scenario: 清理失败不阻断启动
- **WHEN** 启动时孤儿清理抛出错误
- **THEN** 记录警告，运行时仍正常完成后续启动步骤

### Requirement: Agent 运行时周期性回收闲置 agent-scope 沙箱

Agent 运行时启动时 SHALL 在 Docker 可用的前提下启动一个周期性后台任务，按固定间隔调用闲置回收（`sweep_idle`），使闲置超过 `idle_hours` 的 agent-scope 沙箱无需外部触发即被回收。该后台任务 MUST 故障隔离——单次回收失败 SHALL 记录后继续，MUST NOT 终止常驻任务。启动 MUST 幂等——已有运行中的任务时复用而非新建。Docker 不可用时 SHALL NOT 启动该任务。该任务 MUST 不依赖 cron_scheduler/APScheduler（裸 asyncio，与 session 维护一致）。

#### Scenario: Docker 可用时启动周期回收任务
- **WHEN** agent 运行时启动且 Docker 可用
- **THEN** 一个周期性闲置回收后台任务被启动

#### Scenario: 周期任务按间隔调用闲置回收
- **WHEN** 周期回收任务运行且间隔到达
- **THEN** `sweep_idle` 被调用以回收闲置的 agent-scope 沙箱

#### Scenario: 单次回收失败不终止任务
- **WHEN** 某次 `sweep_idle` 调用抛出错误
- **THEN** 记录警告，任务继续运行，下次间隔仍会再次调用

#### Scenario: 重复启动幂等
- **WHEN** 在已有运行中的回收任务时再次请求启动
- **THEN** 复用现有任务，不新建第二个

#### Scenario: Docker 不可用时不启动周期任务
- **WHEN** agent 运行时启动且 Docker 不可用
- **THEN** 不启动周期回收任务
