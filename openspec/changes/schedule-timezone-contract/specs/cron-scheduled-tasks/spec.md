## MODIFIED Requirements

### Requirement: schedule tool for managing scheduled tasks
A single `schedule` built-in tool SHALL let an agent manage scheduled tasks via an `action` parameter (`create`, `list`, `remove`, `run_now`, `pause`, `resume`). It SHALL have `risk_level="low"` and SHALL NOT require human approval. The tool SHALL perform all mutations through the running `CronScheduler` instance obtained via `cron_scheduler.current()` — never by writing `schedule_store` directly. `create` SHALL accept `task_type` (default `generate`) and `notify_text`, enforcing the per-type validation (notify requires `notify_text` + delivery target; generate/action require `message`) and returning a clean error string rather than raising on a validation failure; its tool description SHALL carry the type-deciding question ("does the message content need information only known at send time?") plus the creation-time finalize-and-confirm flow for notify copy. `create` SHALL stamp the task's owner from the execution principal (`tool_context.principal.user_id`) when available, falling back to the `user_id` parameter only when no principal is present — the model-supplied parameter MUST NOT override an available principal. `create` SHALL return the new task's id; `pause`/`resume` SHALL toggle the task's `enabled` flag and deregister/register the APScheduler job accordingly; `run_now` SHALL fire the task immediately via a public scheduler method. When no scheduler is running (one-shot CLI run, or `scheduling.enabled=false`), mutations SHALL still persist to the store and the tool result SHALL state truthfully that the task takes effect when the agent service is running — the tool MUST NOT report the task as active.

The `schedule` tool's parameter contract SHALL be carried in the **tool schema delivered to the model** (the model receives the schema, not the Python function's docstring body): `action`, `schedule_kind`, `task_type`, and `notify_target_type` SHALL be declared as enumerated parameters (via `Literal`) so the model receives their allowed values, and every parameter SHALL carry a description (via `Annotated`) so per-parameter guidance reaches the model. Because `schedule_kind` is enumerated, the model cannot emit a non-member value such as `run_at` (the forgiving normalization underneath remains for non-model callers). The `task_type` parameter description SHALL convey the notify/generate/action selection rule and the default `generate`.

The `timezone` parameter SHALL default to unspecified (empty), NOT to a hardcoded `"UTC"`; when the model does not supply a timezone, `create` SHALL pass it through as absent (`None`) so the deployment-default resolution applies (see "Timezone resolution is local-clock and DST-safe"). The `timezone` and `cron_expr` parameter descriptions SHALL state that cron fields are the **local wall-clock time of the task timezone** and MUST NOT be pre-converted to UTC, and that an unspecified timezone uses the deployment default while an explicit timezone is set only when the user names one. On a successful `create`, the tool result SHALL state the task's next fire time in **both the task timezone and UTC**.

#### Scenario: Agent creates a notify task with frozen copy
- **WHEN** an agent calls `schedule(action="create", task_type="notify", notify_text="📅 晨会提醒：9:00 准时开始", schedule_kind="cron", cron_expr="0 9 * * 1-5")`
- **THEN** the task is created with `task_type="notify"`, fires agent-free, and its id is returned

#### Scenario: Notify creation without copy is rejected
- **WHEN** an agent calls `schedule(action="create", task_type="notify")` without `notify_text`
- **THEN** the tool returns a validation error string without raising

#### Scenario: Agent creates a schedule without approval
- **WHEN** an agent calls `schedule(action="create", schedule_kind="cron", cron_expr=..., message=...)` while the scheduler is running
- **THEN** a task is created with `source="tool"`, its APScheduler job is registered immediately (fires on time with no restart), and its id is returned — with no approval gate

#### Scenario: Agent pauses and resumes a schedule
- **WHEN** an agent calls `schedule(action="pause", task_id=...)` then later `schedule(action="resume", task_id=...)`
- **THEN** the task's `enabled` flag is set to false then true, and the APScheduler job is deregistered then re-registered

#### Scenario: Agent removes a schedule
- **WHEN** an agent calls `schedule(action="remove", task_id=...)` with a valid id
- **THEN** the task is deleted from `scheduled_tasks` and deregistered from the scheduler

#### Scenario: run_now fires immediately
- **WHEN** an agent calls `schedule(action="run_now", task_id=...)`
- **THEN** the task fires once immediately via the scheduler's public API without altering its normal schedule

#### Scenario: Removing non-existent task returns error message
- **WHEN** an agent calls `schedule(action="remove", task_id="nonexistent")`
- **THEN** the tool returns an error string without raising an exception

#### Scenario: Create without a running scheduler degrades honestly
- **WHEN** an agent calls `schedule(action="create", ...)` and `cron_scheduler.current()` is None
- **THEN** the task is persisted to the store and the tool result states it will take effect when the agent service is running, not that it is active now

#### Scenario: Task owner comes from the execution principal
- **WHEN** an agent calls `schedule(action="create", user_id="whatever-the-model-typed")` with a `tool_context` carrying a resolved principal
- **THEN** the created task's `user_id` is the principal's `user_id`, not the model-supplied parameter

#### Scenario: Model receives task_type and schedule_kind enums in the schema
- **WHEN** the `schedule` tool schema is built by the schema builder and delivered to the model
- **THEN** the `task_type` parameter exposes the enum `["notify", "generate", "action"]` with a description conveying the selection rule, and the `schedule_kind` parameter exposes the enum `["cron", "once", "interval"]`

#### Scenario: timezone parameter carries the no-pre-convert contract
- **WHEN** the `schedule` tool schema is built
- **THEN** the `timezone` (and `cron_expr`) parameter descriptions state that cron fields are the task timezone's local wall-clock time and MUST NOT be pre-converted to UTC, and that an unspecified timezone uses the deployment default

#### Scenario: Unspecified timezone is passed through, not forced to UTC
- **WHEN** an agent calls `schedule(action="create", schedule_kind="cron", cron_expr="0 18 * * *", message=...)` with no `timezone`
- **THEN** the persisted task does not carry a hardcoded `"UTC"` that defeats the fallback, and the scheduler resolves the effective timezone from `agent.scheduling.default_timezone`

#### Scenario: Create result states the next fire time in task timezone and UTC
- **WHEN** an agent creates a cron task on a running scheduler
- **THEN** the tool result states the next fire time in both the task timezone and UTC, and the task's `next_run_at` is populated

## ADDED Requirements

### Requirement: Timezone resolution is local-clock and DST-safe
The system SHALL resolve a scheduled task's effective timezone with the precedence **explicit per-task `timezone` > `agent.scheduling.default_timezone` > `UTC`**. Cron fields SHALL be interpreted in the resolved timezone (APScheduler `CronTrigger` timezone) as **local wall-clock time**. The system SHALL persist the cron expression and the timezone **as given** and SHALL NOT normalize a recurring schedule to a fixed UTC offset at creation time, so a recurring task fires at the same local wall-clock time across daylight-saving transitions. Neither the model nor the tool layer SHALL perform timezone arithmetic when constructing a task — the model supplies the user's stated wall-clock time plus (optionally) a timezone name, and conversion is the scheduler's concern at fire time.

#### Scenario: Cron is interpreted in the task timezone
- **WHEN** a task is registered with `cron_expr="0 18 * * *"` and `timezone="Asia/Shanghai"`
- **THEN** it fires at 18:00 Asia/Shanghai — not 18:00 UTC, and not 10:00 Asia/Shanghai

#### Scenario: Empty timezone resolves to the deployment default
- **WHEN** a task is created with no timezone while `agent.scheduling.default_timezone="Asia/Shanghai"`
- **THEN** it is registered against `Asia/Shanghai` and fires at the intended local wall-clock time

#### Scenario: No double conversion of the wall-clock time
- **WHEN** a user asks for 20:34 in a named timezone and the task is created
- **THEN** the stored cron fields equal the stated wall-clock (`34 20`) and the timezone equals the named zone — the wall-clock is never pre-shifted to UTC

#### Scenario: Recurring schedule follows daylight-saving
- **WHEN** a daily task is stored as a local cron expression plus an IANA timezone that observes DST
- **THEN** it fires at the same local wall-clock time before and after a daylight-saving transition (no fixed-UTC-offset drift), because the schedule was not normalized to UTC at creation
