## ADDED Requirements

### Requirement: 进程内周期触发 session 清理

平台 SHALL 提供一个进程内常驻后台循环，按 `session_cleanup_interval_seconds` 周期调用既有的 session 清理入口（`maybe_run_maintenance`），使 TTL 过期删除与磁盘容量驱逐在**无 session 写入活动**期间也能自动发生，而不再仅依赖 `save()` 的被动触发。该后台循环 MUST 复用既有清理入口（含其时间门、TTL、容量、SB2 sandbox release），MUST NOT 重复实现清理语义，MUST NOT 改变既有清理行为。

#### Scenario: 无活动期循环按 interval 触发清理
- **WHEN** 后台维护循环以注入的 interval 运行且期间无任何 `save()` 写入活动
- **THEN** 循环每经过一个 interval 调用一次 `maybe_run_maintenance`，过期 session 与超容量 session 被清理

#### Scenario: 循环复用既有清理入口
- **WHEN** 后台维护循环触发一次清理
- **THEN** 它通过调用既有 `maybe_run_maintenance` 完成，不另行实现 TTL 判定或容量驱逐逻辑

### Requirement: 单次清理失败不杀常驻循环

后台维护循环的每一轮触发 MUST 被故障隔离：单次清理抛出异常时，平台 SHALL 以 warning 级别记录该异常（不静默吞掉）并**继续下一轮循环**，MUST NOT 让一次失败终止常驻任务。

#### Scenario: 一次清理异常后循环继续
- **WHEN** 某一轮 `maybe_run_maintenance` 抛出异常
- **THEN** 平台以 warning 记录该异常，循环不退出，在下一个 interval 继续触发清理

### Requirement: 触发器启停接入 server lifespan

平台 SHALL 在 server 启动（lifespan 启动段）时启动该后台维护任务，并在 server 关停（lifespan 关停段）时取消它，取消后 MUST 不残留任务。启动入口 MUST 幂等：已有任务在运行时再次启动 MUST 返回现有任务而非重复创建。

#### Scenario: 启动创建任务、关停取消且无残留
- **WHEN** 启动后台维护任务后再调用停止入口
- **THEN** 任务被取消、`CancelledError` 被吞掉、模块级任务句柄被置 None，不残留运行中的任务

#### Scenario: 重复启动幂等
- **WHEN** 后台维护任务已在运行时再次调用启动入口
- **THEN** 返回现有任务，不创建第二个任务

#### Scenario: 无任务时停止为 no-op
- **WHEN** 没有运行中的维护任务时调用停止入口
- **THEN** 调用安全返回，不抛异常

### Requirement: CLI 一次性进程不启常驻触发器

平台 SHALL 仅在 server lifespan 中常驻该后台维护任务。CLI 一次性执行路径（`run_sync`）MUST NOT 启动该常驻任务——CLI 进程短暂，既有 `save()` 被动触发已足够。

#### Scenario: CLI 调用不启动常驻维护任务
- **WHEN** 通过 CLI 一次性执行路径运行
- **THEN** 不创建常驻后台维护任务，模块级维护任务句柄保持为 None

### Requirement: 触发机制不依赖外部调度器

该周期触发 MUST 以进程内裸 `asyncio` 后台任务实现，MUST NOT 经由 `cron_scheduler` / APScheduler 或任何外部调度器，与用户级定时任务功能（scheduling 域）解耦，且 MUST NOT 引入新依赖。

#### Scenario: 触发不挂 cron_scheduler
- **WHEN** 周期触发 session 清理
- **THEN** 触发由进程内 asyncio 后台循环完成，不调用 `cron_scheduler` / APScheduler、不引入新依赖
