# cron-scheduled-tasks Delta

## ADDED Requirements

### Requirement: Run-state writeback is field-selective

`schedule_store.update_run_state` SHALL update **only the columns the caller explicitly passes**（PATCH 语义）：未传入的列 MUST 保持原值不变。写 `last_run_at`/`last_status`/`last_error` MUST NOT 清除或改写 `next_run_at`，写 `next_run_at`（如注册时 backfill）MUST NOT 清除运行状态列。「显式置空」与「未传」SHALL 用 sentinel 区分（传 `None` 即显式置 NULL 的旧用法不复存在——现有调用方均按部分更新意图书写）。

#### Scenario: 写状态列不影响 next_run_at
- **WHEN** 一个任务已有 `next_run_at`，随后 `update_run_state(task_id, last_run_at=..., last_status="ok")` 被调用（未传 `next_run_at`）
- **THEN** `last_run_at`/`last_status` 更新，`next_run_at` 保持原值不变

#### Scenario: 写 next_run_at 不影响状态列
- **WHEN** 一个任务已有 `last_status="error"` 与 `last_error`，随后 `update_run_state(task_id, next_run_at=...)` 被调用
- **THEN** `next_run_at` 更新，`last_status`/`last_error`/`last_run_at` 保持原值不变

#### Scenario: 贯通接缝——真实 fire 后状态与网格并存
- **WHEN** 一个 interval 任务经真实 `_fire` 路径（仅 stub agent run）完成一次触发，且下一个 tick 已运行
- **THEN** store 中该任务同时持有：claim 时推进的 `next_run_at` 网格值、本次 fire 的 `last_run_at`/`last_status`——二者互不抹除

## MODIFIED Requirements

### Requirement: Schedule kinds cron, one-shot, and interval

The system SHALL support three schedule kinds, each defining how the task's next occurrence (`next_run_at`) is computed: `cron` (5-field expression; the next occurrence after the current base time), `once` (an absolute timestamp or relative duration; a single occurrence), and `interval` (a fixed period; the next occurrence is the **previous scheduled occurrence — the persisted `next_run_at` grid — plus the period**, fast-forwarded in whole periods to the first future occurrence when stale, or now-plus-period when there is no prior occurrence). Interval cadence SHALL be **fixed-rate on the schedule grid**: a fire MUST NOT re-anchor the next occurrence to the run's completion time or to the tick time. `schedule_kind` MUST be validated at task creation: a value outside `{cron, once, interval}` MUST be rejected with a clear `ValueError` (e.g. `invalid schedule_kind: 'run_at' (cron/once/interval)`) and MUST NOT be persisted. As a forgiving normalization for the common model confusion of passing the parameter name as the kind, `schedule_kind="run_at"` MUST be treated as `"once"` at creation (then the one-shot `run_at` normalization applies). Next-occurrence computation SHALL be engine-internal (no dependency on an external in-memory trigger registry).

#### Scenario: Cron schedule
- **WHEN** a task with `schedule_kind="cron"` and `cron_expr="0 9 * * 1-5"` is registered
- **THEN** its `next_run_at` resolves to 09:00 on the next weekday in the task timezone, and it fires at that time

#### Scenario: One-shot schedule
- **WHEN** a task with `schedule_kind="once"` and `run_at` 30 minutes in the future is registered
- **THEN** it fires once at that time and is then marked `completed` (not re-run)

#### Scenario: Interval schedule
- **WHEN** a task with `schedule_kind="interval"` and `interval_seconds=5400` (90 minutes) is registered
- **THEN** its `next_run_at` advances by 90 minutes each occurrence and it fires roughly every 90 minutes

#### Scenario: Interval 节奏不被 fire 重锚（无累积漂移）
- **WHEN** 一个 60 秒 interval 任务连续多次真实触发（含运行耗时与 tick 延迟）
- **THEN** 每次 fire 后 `next_run_at` 均等于「前一计划时刻 + 60s」的网格值（过期则整周期快进），相邻触发间隔不随触发次数累积增长（AAA-8288 判据：连续 10 次触发间隔 ∈ [60, 60+tick) 秒）

#### Scenario: run_at is aliased to once
- **WHEN** a one-shot task is created with `schedule_kind="run_at"` and a valid `run_at` time
- **THEN** it is normalized to `schedule_kind="once"`, persisted as a one-shot, and fires at `run_at` (no registration failure)

#### Scenario: invalid schedule_kind is rejected at creation
- **WHEN** a task is created with a `schedule_kind` that is not one of `cron`/`once`/`interval` (and not the `run_at` alias)
- **THEN** creation raises a clear `ValueError` naming the allowed kinds and persists no row; the `schedule` tool surfaces it as an explanatory error so the agent can retry with a valid kind

### Requirement: Advance-before-execute decouples cadence from run duration

For a recurring (`cron`/`interval`) due task, the scheduler SHALL **advance `next_run_at` to the next occurrence BEFORE executing the run**, inside the same concurrency-protected claim. Firing SHALL NOT block the tick loop (each run is dispatched so the tick can continue selecting/advancing other due tasks). Consequently a single run whose duration exceeds the task's interval SHALL NOT cause the following occurrence to be dropped or coalesced: the next occurrence's `next_run_at` is already set and will be picked up on a subsequent tick. Advancing before execution gives **at-most-once** semantics for recurring tasks (a crash mid-run does not re-fire the same occurrence). **The post-fire run-state writeback SHALL preserve the claimed `next_run_at`**（见「Run-state writeback is field-selective」）——fire 完成后的下一个 tick MUST NOT 依赖 backfill 分支重算调度时刻。One-shot (`once`) tasks SHALL NOT be advanced; their outcome (success or failure) is governed by the one-shot terminal-outcome policy in "Fire-time revalidation against the store" — a failed `once` fire terminates the task and MUST NOT leave it due for repeated automatic retries.

#### Scenario: Slow run does not drop the next occurrence
- **WHEN** an `interval` task whose single run takes longer than its `interval_seconds` fires
- **THEN** its `next_run_at` was advanced before the run began, and the next occurrence fires on a later tick rather than being silently skipped or coalesced away

#### Scenario: Recurring task is not double-fired for one occurrence
- **WHEN** a recurring task is claimed and its `next_run_at` advanced, then the process crashes during the run
- **THEN** on restart the same occurrence is not re-fired (at-most-once); scheduling resumes from the already-advanced `next_run_at`

#### Scenario: fire 完成后的写回保留已推进的 next_run_at
- **WHEN** 一个 recurring 任务被 claim（`next_run_at` 已推进到未来）且其 run 经真实 `_fire` 路径完成、运行状态写回发生
- **THEN** store 中 `next_run_at` 仍等于 claim 时推进的值（非 NULL、未被重算），下一次触发按该网格值发生

#### Scenario: One-shot is not advanced
- **WHEN** a `once` task is claimed to fire
- **THEN** its `next_run_at` is not advanced to a future occurrence; completion is governed by one-shot completion handling

### Requirement: Fire-time revalidation against the store

Before executing, a fired job SHALL re-read its task row from the store by id. If the row is missing or `enabled=0`, the fire SHALL be skipped with a warning log and the stale job deregistered. The re-read row SHALL be used as the execution payload (not the dict captured at registration time). A `once` task that fires successfully SHALL be marked completed (`enabled=0`, `last_status="completed"`). A `once` task whose fire **fails**（agent error 或 delivery error）SHALL be **terminally closed**: `enabled=0`、`last_status="error"`、`last_error` 保留失败原因——它 MUST NOT 停留在过去的 `next_run_at` 上被后续 tick 自动重试（禁止无退避热重试）。手动 `run_now` 仍可用于人工重试（不改变 enabled/schedule）。

#### Scenario: Deleted task never fires
- **WHEN** a job fires whose store row was deleted by a writer that bypassed the facade
- **THEN** execution is skipped, a warning is logged, and the job is deregistered

#### Scenario: Disabled task never fires
- **WHEN** a job fires whose store row has `enabled=0`
- **THEN** execution is skipped and the job is deregistered

#### Scenario: Once task marked completed after firing
- **WHEN** a `once` task fires successfully
- **THEN** its row is updated to `enabled=0` and `last_status="completed"`, and it is not re-registered on next boot

#### Scenario: 失败的 once 任务被终结而非热重试
- **WHEN** 一个 `once` 任务 fire 失败（如 agent run 抛错或投递失败）
- **THEN** 其行被更新为 `enabled=0`、`last_status="error"`（`last_error` 含失败原因），后续 tick 不再触发它；run history 中保留该次 error 记录

#### Scenario: 失败 once 在后续 tick 不重复烧钱
- **WHEN** 一个 `generate` 型 once 任务因 LLM 网关持续故障 fire 失败，随后调度器继续运行多个 tick
- **THEN** 该任务在首次失败后不再产生任何新的 agent run（对比修复前：每 ~2 tick 重跑一次直至故障恢复）

### Requirement: Robust run_at parsing and write-time normalization

The one-shot `run_at` parser SHALL tolerate common non-strict ISO forms in addition to strict ISO-8601 and relative durations (`+30m`/`2h`): a trailing timezone-name suffix (` UTC`/` GMT`) MUST be normalized to a numeric offset before parsing, and a trailing `Z` MUST be accepted. **A naive ISO form（无 offset）SHALL 按任务的 resolved timezone（显式 per-task `timezone` > `agent.scheduling.default_timezone` > `UTC`）解释为 aware 时间——MUST NOT 按宿主机系统时区解释；解析器 SHALL 接收任务时区作为参数。** When a `once` task is created via the `schedule` tool, the system SHALL normalize `run_at` through that same parser（携带任务时区）and persist the canonical ISO form (with explicit offset); an unparseable `run_at` MUST be rejected at create time with an explanatory error and MUST NOT be stored. 存储层 MUST NOT 出现 naive（无 offset）的 `run_at`/`next_run_at` 时间值。

#### Scenario: run_at with UTC suffix parses
- **WHEN** `_parse_run_at("2026-06-14 08:07:19 UTC")` is evaluated
- **THEN** it resolves to the corresponding UTC datetime without raising

#### Scenario: strict ISO and relative durations still work
- **WHEN** `_parse_run_at("2026-06-14T08:07:19Z")` and `_parse_run_at("+30m")` are evaluated
- **THEN** both resolve correctly (absolute UTC; now + 30 minutes)

#### Scenario: naive run_at 按任务时区解释
- **WHEN** 一个 `once` 任务以 `run_at="2026-07-08 09:00"`（无 offset）、`timezone="Asia/Shanghai"` 创建，宿主机系统时区为 UTC
- **THEN** 持久化的 `run_at` 为 `2026-07-08T09:00:00+08:00`（等价 01:00 UTC），任务在北京时间 09:00 触发——不是 09:00 UTC

#### Scenario: create normalizes run_at to canonical ISO
- **WHEN** a `once` task is created via the `schedule` tool with `run_at="2026-06-14 08:07:19 UTC"`
- **THEN** the stored `run_at` is canonical ISO with an explicit offset (e.g. `2026-06-14T08:07:19+00:00`)

#### Scenario: create rejects an unparseable run_at
- **WHEN** a `once` task is created with a `run_at` the parser cannot resolve
- **THEN** the tool returns an explanatory error and no row is persisted

### Requirement: Timezone resolution is local-clock and DST-safe

The system SHALL resolve a scheduled task's effective timezone with the precedence **explicit per-task `timezone` > `agent.scheduling.default_timezone` > `UTC`**. Cron fields SHALL be interpreted in the resolved timezone (APScheduler `CronTrigger` timezone) as **local wall-clock time**; **a one-shot task's naive `run_at` SHALL likewise be interpreted in the resolved timezone as local wall-clock time**（见「Robust run_at parsing and write-time normalization」）. The system SHALL persist the cron expression and the timezone **as given** and SHALL NOT normalize a recurring schedule to a fixed UTC offset at creation time, so a recurring task fires at the same local wall-clock time across daylight-saving transitions. Neither the model nor the tool layer SHALL perform timezone arithmetic when constructing a task — the model supplies the user's stated wall-clock time plus (optionally) a timezone name, and conversion is the scheduler's concern at fire time.

#### Scenario: Cron is interpreted in the task timezone
- **WHEN** a task is registered with `cron_expr="0 18 * * *"` and `timezone="Asia/Shanghai"`
- **THEN** it fires at 18:00 Asia/Shanghai — not 18:00 UTC, and not 10:00 Asia/Shanghai

#### Scenario: one-shot 钟面时间按任务时区解释
- **WHEN** 用户说「明早 9 点提醒我」（Asia/Shanghai 语境），任务以 naive `run_at` + `timezone="Asia/Shanghai"` 创建，部署宿主机时区任意
- **THEN** 任务在 Asia/Shanghai 的 09:00 触发；宿主机系统时区不参与解释

#### Scenario: Empty timezone resolves to the deployment default
- **WHEN** a task is created with no timezone while `agent.scheduling.default_timezone="Asia/Shanghai"`
- **THEN** it is registered against `Asia/Shanghai` and fires at the intended local wall-clock time

#### Scenario: No double conversion of the wall-clock time
- **WHEN** a user asks for 20:34 in a named timezone and the task is created
- **THEN** the stored cron fields equal the stated wall-clock (`34 20`) and the timezone equals the named zone — the wall-clock is never pre-shifted to UTC

#### Scenario: Recurring schedule follows daylight-saving
- **WHEN** a daily task is stored as a local cron expression plus an IANA timezone that observes DST
- **THEN** it fires at the same local wall-clock time before and after a daylight-saving transition (no fixed-UTC-offset drift), because the schedule was not normalized to UTC at creation
