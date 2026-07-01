## ADDED Requirements

### Requirement: Durable next_run_at poll engine
The scheduler SHALL drive firing from a **persisted `next_run_at` per task** plus a lightweight in-process **tick loop**, not from an in-memory trigger registry. On each tick the scheduler SHALL select the tasks whose `next_run_at <= now` ("due tasks") and fire them. The tick loop SHALL run as an agent-process asyncio background task started at boot and stopped at shutdown. Because fleetent runs the scheduler in a **single process**, cross-process file locking is NOT required; the engine SHALL use in-process concurrency protection so a due task is claimed and advanced at most once per tick even under overlapping ticks.

#### Scenario: Due tasks selected by persisted next_run_at
- **WHEN** a tick runs and a recurring task's `next_run_at` is at or before now
- **THEN** the task is selected as due and fired; a task whose `next_run_at` is in the future is not fired

#### Scenario: Tick loop lifecycle bound to the agent process
- **WHEN** the agent boots with scheduling enabled
- **THEN** a background tick loop starts; on agent shutdown the loop stops cleanly without leaking a task

### Requirement: Advance-before-execute decouples cadence from run duration
For a recurring (`cron`/`interval`) due task, the scheduler SHALL **advance `next_run_at` to the next occurrence BEFORE executing the run**, inside the same concurrency-protected claim. Firing SHALL NOT block the tick loop (each run is dispatched so the tick can continue selecting/advancing other due tasks). Consequently a single run whose duration exceeds the task's interval SHALL NOT cause the following occurrence to be dropped or coalesced: the next occurrence's `next_run_at` is already set and will be picked up on a subsequent tick. Advancing before execution gives **at-most-once** semantics for recurring tasks (a crash mid-run does not re-fire the same occurrence). One-shot (`once`) tasks SHALL NOT be advanced (so they may still retry on restart until completed).

#### Scenario: Slow run does not drop the next occurrence
- **WHEN** an `interval` task whose single run takes longer than its `interval_seconds` fires
- **THEN** its `next_run_at` was advanced before the run began, and the next occurrence fires on a later tick rather than being silently skipped or coalesced away

#### Scenario: Recurring task is not double-fired for one occurrence
- **WHEN** a recurring task is claimed and its `next_run_at` advanced, then the process crashes during the run
- **THEN** on restart the same occurrence is not re-fired (at-most-once); scheduling resumes from the already-advanced `next_run_at`

#### Scenario: One-shot is not advanced
- **WHEN** a `once` task is claimed to fire
- **THEN** its `next_run_at` is not advanced to a future occurrence; completion is governed by one-shot completion handling

### Requirement: Bounded parallel execution
The scheduler SHALL execute due-task runs with a **bounded concurrency limit** (configurable), rather than a strict serial single-instance constraint. A slow or hung run SHALL NOT block the firing of other due tasks up to the concurrency bound. The bound SHALL be resolvable from agent scheduling configuration with a safe default.

#### Scenario: Concurrent due tasks run in parallel up to the bound
- **WHEN** multiple tasks are due on the same tick and the concurrency bound is greater than one
- **THEN** they run concurrently up to the bound; a long-running task does not prevent the others from firing

#### Scenario: Concurrency bound is honored
- **WHEN** more tasks are due than the configured concurrency bound
- **THEN** at most the bound number of runs execute at once; the remainder run as slots free up

## MODIFIED Requirements

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task becomes due (its persisted `next_run_at <= now` on a tick), the scheduler SHALL fire **according to the task's `task_type`**: `notify` sends `notify_text` verbatim via the fire-time connector snapshot **without invoking `agent_loop.run`**; `generate` and `action` call `agent_loop.run()` with the task's `message`, `user_id`, resolved agent context, and the fire-time `outbound_connectors` snapshot. For `generate`, the run additionally receives the scheduled-run delivery statement AND is invoked with outbound-tool suppression (`suppress_outbound_tools=True`) so the run produces only the notification body and the scheduler performs the sole delivery (`send_im_message`/`send_file` are absent from a generate run's tool schema). For `action`, the run retains the outbound tools (so the agent delivers via its own tools and the scheduler does not broadcast). The fire SHALL NOT block the tick loop (the run is dispatched so the loop keeps selecting and advancing other due tasks), and the run result SHALL be recorded in the observability trace AND as a run-history row (see capability `cron-run-history`). `last_status` SHALL reflect the **task intent** outcome per type — notify: delivery outcome; generate: run + delivery outcome; action: run outcome — never merely "the delivery API call succeeded". A due occurrence SHALL NOT be silently dropped: an occurrence that cannot run (e.g. its owner is skipped/unverified) SHALL be recorded as a `skipped` run rather than vanishing without a trace.

#### Scenario: Notify fire bypasses the agent
- **WHEN** a `notify` task becomes due
- **THEN** the scheduler sends `notify_text` to the resolved target without calling `agent_loop.run`

#### Scenario: Agent run triggered on schedule
- **WHEN** a `generate` or `action` task becomes due
- **THEN** `agent_loop.run()` is invoked with the task's message and user_id without blocking the tick loop

#### Scenario: Action fire can deliver via IM tools
- **WHEN** an `action` task fires whose message asks the agent to send a message/notification to a channel or user
- **THEN** the agent run receives the fire-time `outbound_connectors` snapshot AND retains the outbound tools, so an outbound IM tool invoked inside the run reaches the live connector (the run is not told "no connector available")

#### Scenario: Generate fire produces content but does not self-deliver
- **WHEN** a `generate` task fires
- **THEN** `agent_loop.run()` is invoked with `suppress_outbound_tools=True` so `send_im_message`/`send_file` are absent from the run's schema, and the final reply is delivered solely by the scheduler's broadcast

#### Scenario: No connectors available degrades cleanly
- **WHEN** a task fires while no IM connector is registered for the agent
- **THEN** `agent_loop.run()` receives an empty `outbound_connectors` mapping and the run proceeds without error

#### Scenario: Run outcome recorded in runtime-state columns and history
- **WHEN** a triggered agent run completes or fails
- **THEN** the task's `last_run_at`, `last_status`, and (on failure) `last_error` are updated, a run-history row is appended, and the run is written to the eval trace

#### Scenario: Unrunnable due occurrence is recorded as skipped
- **WHEN** a task becomes due but its fire-time principal cannot be verified (owner blocked/vanished) so it does not run
- **THEN** a `skipped` run-history row is recorded (the occurrence is not silently dropped)

### Requirement: Schedule kinds cron, one-shot, and interval
The system SHALL support three schedule kinds, each defining how the task's next occurrence (`next_run_at`) is computed: `cron` (5-field expression; the next occurrence after the current base time), `once` (an absolute timestamp or relative duration; a single occurrence), and `interval` (a fixed period; the next occurrence is the previous run time plus the period, or now-plus-period when there is no previous run). `schedule_kind` MUST be validated at task creation: a value outside `{cron, once, interval}` MUST be rejected with a clear `ValueError` (e.g. `invalid schedule_kind: 'run_at' (cron/once/interval)`) and MUST NOT be persisted. As a forgiving normalization for the common model confusion of passing the parameter name as the kind, `schedule_kind="run_at"` MUST be treated as `"once"` at creation (then the one-shot `run_at` normalization applies). Next-occurrence computation SHALL be engine-internal (no dependency on an external in-memory trigger registry).

#### Scenario: Cron schedule
- **WHEN** a task with `schedule_kind="cron"` and `cron_expr="0 9 * * 1-5"` is registered
- **THEN** its `next_run_at` resolves to 09:00 on the next weekday in the task timezone, and it fires at that time

#### Scenario: One-shot schedule
- **WHEN** a task with `schedule_kind="once"` and `run_at` 30 minutes in the future is registered
- **THEN** it fires once at that time and is then marked `completed` (not re-run)

#### Scenario: Interval schedule
- **WHEN** a task with `schedule_kind="interval"` and `interval_seconds=5400` (90 minutes) is registered
- **THEN** its `next_run_at` advances by 90 minutes each occurrence and it fires roughly every 90 minutes

#### Scenario: run_at is aliased to once
- **WHEN** a one-shot task is created with `schedule_kind="run_at"` and a valid `run_at` time
- **THEN** it is normalized to `schedule_kind="once"`, persisted as a one-shot, and fires at `run_at` (no registration failure)

#### Scenario: invalid schedule_kind is rejected at creation
- **WHEN** a task is created with a `schedule_kind` that is not one of `cron`/`once`/`interval` (and not the `run_at` alias)
- **THEN** creation raises a clear `ValueError` naming the allowed kinds and persists no row; the `schedule` tool surfaces it as an explanatory error so the agent can retry with a valid kind

### Requirement: Missed-run handling on restart
The scheduler SHALL avoid burst-firing missed runs after the agent process was down by **fast-forwarding stale schedules** rather than replaying each missed slot. On boot (and on each tick), a recurring task whose `next_run_at` is stale (more than one period in the past, e.g. because the process was down) SHALL be fast-forwarded to its next future occurrence, firing **at most once** for the missed window (combined with advance-before-execute). A `once` task whose `run_at` elapsed beyond a bounded recovery window while the process was down SHALL be marked `completed` without firing; within the recovery window it MAY fire once.

#### Scenario: Recurring task fast-forwards missed runs
- **WHEN** the agent process was down across several scheduled fire times and then boots
- **THEN** the recurring task fires at most once for the missed window and its `next_run_at` is fast-forwarded to the next future occurrence, not fired once per missed slot

#### Scenario: Expired one-shot is not fired late
- **WHEN** a `once` task's `run_at` passed beyond the recovery window while the process was down
- **THEN** on boot it is marked `completed` and does not fire

### Requirement: Scheduler global settings
The scheduler SHALL read its runtime settings from the **agent configuration** (`agent.yaml` `scheduling`), not from Platform settings. In addition to `enabled` and `default_timezone`, the scheduling settings SHALL expose the **tick interval** and the **bounded execution concurrency** (both with safe defaults) so the poll cadence and parallelism are configurable per agent.

#### Scenario: Scheduler disabled
- **WHEN** `agent.scheduling.enabled=false`
- **THEN** `agent_app` boot does not start the tick loop

#### Scenario: Default timezone is configured
- **WHEN** a persisted task does not define timezone
- **THEN** the scheduler uses `agent.scheduling.default_timezone`

#### Scenario: Tick interval and concurrency are configurable
- **WHEN** `agent.scheduling` defines a tick interval and/or execution concurrency
- **THEN** the poll loop uses the configured tick interval and the bounded executor uses the configured concurrency; unset values fall back to safe defaults
