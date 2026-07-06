# cron-scheduled-tasks Delta

## MODIFIED Requirements

### Requirement: Missed-run handling on restart

The scheduler SHALL avoid burst-firing missed runs after the agent process was down by **fast-forwarding stale schedules** rather than replaying each missed slot. On boot (and on each tick), a recurring task whose `next_run_at` is stale (more than one period in the past, e.g. because the process was down) SHALL be fast-forwarded to its next future occurrence, firing **at most once** for the missed window (combined with advance-before-execute). **对 `cron` 型定点任务，补跑 SHALL 有陈旧度上界（宽限窗）`min(半周期, 2 小时)`：迟到在宽限内补跑一次；超过宽限则本次 MUST NOT 补跑——记一条 `missed` run-history 行并 fast-forward 到下一未来时刻（宕机三天的 daily digest 不在重启时补发陈旧内容）。`interval` 型不设陈旧度上界（固定周期任务的一次补跑内容即时效内容），维持至多补跑一次。** A `once` task whose `run_at` elapsed beyond a bounded recovery window while the process was down SHALL be marked `completed` without firing; within the recovery window it MAY fire once.

#### Scenario: Recurring task fast-forwards missed runs
- **WHEN** the agent process was down across several scheduled fire times and then boots
- **THEN** the recurring task fires at most once for the missed window and its `next_run_at` is fast-forwarded to the next future occurrence, not fired once per missed slot

#### Scenario: 宽限内的 cron 定点任务补跑一次
- **WHEN** 一个每日 09:00 的 cron 任务因进程重启在 09:40 才恢复（迟到 40 分钟 < min(12h, 2h)=2h）
- **THEN** 该任务补跑一次，随后 `next_run_at` 指向次日 09:00

#### Scenario: 超宽限的 cron 定点任务记 missed 不补跑
- **WHEN** 一个每日 09:00 的 cron 任务宕机三天后恢复（迟到远超 2h 宽限）
- **THEN** 本次不触发任何 run，追加一条 `status="missed"` 的 run-history 行，`next_run_at` fast-forward 到下一个未来 09:00

#### Scenario: interval 任务恢复后补跑一次
- **WHEN** 一个 60s interval 任务宕机 3 天后恢复
- **THEN** 它补跑一次（内容为即时内容，非陈旧回放）并按网格 fast-forward，不逐槽回放

#### Scenario: Expired one-shot is not fired late
- **WHEN** a `once` task's `run_at` passed beyond the recovery window while the process was down
- **THEN** on boot it is marked `completed` and does not fire

### Requirement: Durable next_run_at poll engine

The scheduler SHALL drive firing from a **persisted `next_run_at` per task** plus a lightweight in-process **tick loop**, not from an in-memory trigger registry. On each tick the scheduler SHALL select the tasks whose `next_run_at <= now` ("due tasks") and fire them. The tick loop SHALL run as an agent-process asyncio background task started at boot and stopped at shutdown. Because fleetent runs the scheduler in a **single process**, cross-process file locking is NOT required; the engine SHALL use in-process concurrency protection so a due task is claimed and advanced at most once per tick even under overlapping ticks. **tick 遍历 SHALL 逐行舱壁化：单个任务行的解码、判定或注册异常 SHALL 只跳过该行并记 warning——MUST NOT 中止本次 tick 或影响其余任务（一行损坏的 origin/deliver JSON 不得瘫痪调度器）。tick 间睡眠 SHALL 对齐最近到期时刻：睡眠时长 = `min(tick_interval, 距最早 next_run_at 的剩余时间)`（下界 0.5s 防忙轮询），使触发迟到从 ≤tick_interval 收敛到亚秒级。**

#### Scenario: Due tasks selected by persisted next_run_at
- **WHEN** a tick runs and a recurring task's `next_run_at` is at or before now
- **THEN** the task is selected as due and fired; a task whose `next_run_at` is in the future is not fired

#### Scenario: 一行坏数据不瘫痪调度器
- **WHEN** store 中某任务行的 `origin` 列被外部改成非法 JSON，同时存在其他正常到期任务
- **THEN** 该行被跳过并记 warning，本次 tick 照常触发其余到期任务，后续 tick 不受影响

#### Scenario: 触发时刻对齐到期时间
- **WHEN** 一个任务的 `next_run_at` 距上个 tick 结束 3 秒
- **THEN** 引擎睡眠约 3 秒后即触发（迟到亚秒级），而非等满一个完整 tick_interval

#### Scenario: Tick loop lifecycle bound to the agent process
- **WHEN** the agent boots with scheduling enabled
- **THEN** a background tick loop starts; on agent shutdown the loop stops cleanly without leaking a task

### Requirement: Dynamic tasks survive server restart

Tasks created via the `schedule` tool SHALL be persisted to the agent-side SQLite store and re-registered with APScheduler on every **agent process boot** (`agent_app.boot`), with `next_run_at` recomputed from the current time. Cron jobs SHALL NOT be loaded from YAML files. Re-registration MUST be bulkheaded per task: if registering one task raises (e.g. a malformed `run_at`), the scheduler SHALL log a warning, disable that task (`enabled=0`, so it is not re-loaded on the next boot), and skip it — it MUST NOT abort boot or prevent the remaining tasks from registering. A single bad row is a data problem, never an availability problem. **因坏数据禁用任务时 SHALL best-effort 向该任务的可解析投递目标（origin 或显式 deliver）发送一条禁用告警（含任务名与原因）——禁用 MUST NOT 纯静默发生；告警投递失败只记日志，不影响 boot。**

#### Scenario: Dynamic task re-registered after agent restart
- **WHEN** a task is created via `schedule_store.create()` and the agent process is restarted
- **THEN** the task is active again after `agent_app` starts its scheduler, with a freshly computed `next_run_at`

#### Scenario: Old cron YAML is not loaded
- **WHEN** a legacy cron YAML file exists
- **THEN** scheduler startup does not load static jobs from it

#### Scenario: One malformed task does not crash boot
- **WHEN** the store holds a `once` task whose `run_at` cannot be parsed (e.g. `'2026-06-14 08:07:19 UTC'` survived from an older writer) alongside valid tasks
- **THEN** scheduler start logs a warning for that task, disables it (`enabled=0`), registers all the valid tasks, and the scheduler starts normally — boot completes

#### Scenario: 禁用坏行时用户收到告警
- **WHEN** boot 注册期一个任务因数据损坏被禁用，且其 origin 可解析、连接器在线
- **THEN** origin 会话收到一条「任务 <name> 已因数据问题被停用」的告警；告警失败仅记日志，boot 不受影响

### Requirement: Bounded parallel execution

The scheduler SHALL execute due-task runs with a **bounded concurrency limit** (configurable), rather than a strict serial single-instance constraint. A slow or hung run SHALL NOT block the firing of other due tasks up to the concurrency bound. The bound SHALL be resolvable from agent scheduling configuration with a safe default. **每次 fire 的执行 SHALL 受看门狗超时保护（`scheduling.fire_timeout_seconds`，默认 900，0=关闭）：超时的运行被取消、该次 run 记 `error`（timeout 语义、含已运行时长），其 in-flight 标记与并发槽 SHALL 被释放——一次卡死的运行 MUST NOT 永久占用并发槽或永久阻止该任务的后续触发。**

#### Scenario: Concurrent due tasks run in parallel up to the bound
- **WHEN** multiple tasks are due on the same tick and the concurrency bound is greater than one
- **THEN** they run concurrently up to the bound; a long-running task does not prevent the others from firing

#### Scenario: Concurrency bound is honored
- **WHEN** more tasks are due than the configured concurrency bound
- **THEN** at most the bound number of runs execute at once; the remainder run as slots free up

#### Scenario: 卡死的 fire 被看门狗回收
- **WHEN** 一次 fire 的运行超过 `fire_timeout_seconds` 仍未返回
- **THEN** 该运行被取消，run history 记一条 timeout 语义的 `error` 行，任务的 in-flight 标记与并发槽被释放，该任务与其他任务的后续触发不受影响

#### Scenario: 看门狗可关闭
- **WHEN** `scheduling.fire_timeout_seconds=0`
- **THEN** fire 不设超时（恢复无看门狗行为）

### Requirement: Scheduler global settings

The scheduler SHALL read its runtime settings from the **agent configuration** (`agent.yaml` `scheduling`), not from Platform settings. In addition to `enabled` and `default_timezone`, the scheduling settings SHALL expose the **tick interval** and the **bounded execution concurrency** (both with safe defaults) so the poll cadence and parallelism are configurable per agent. **The settings SHALL additionally expose `fire_timeout_seconds`（per-fire 看门狗超时，默认 900，0=关闭）。**

#### Scenario: Scheduler disabled
- **WHEN** `agent.scheduling.enabled=false`
- **THEN** `agent_app` boot does not start the tick loop

#### Scenario: Default timezone is configured
- **WHEN** a persisted task does not define timezone
- **THEN** the scheduler uses `agent.scheduling.default_timezone`

#### Scenario: Tick interval and concurrency are configurable
- **WHEN** `agent.scheduling` defines a tick interval and/or execution concurrency
- **THEN** the poll loop uses the configured tick interval and the bounded executor uses the configured concurrency; unset values fall back to safe defaults

#### Scenario: fire 超时可配置
- **WHEN** `agent.scheduling.fire_timeout_seconds` 被设置
- **THEN** 每次 fire 的看门狗采用该值；未设置时默认 900 秒
