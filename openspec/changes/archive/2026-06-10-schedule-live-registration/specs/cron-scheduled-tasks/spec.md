## ADDED Requirements

### Requirement: Live mutation through a single owner
All scheduled-task mutations (create / remove / enable-disable / run-now) SHALL go through public `CronScheduler` methods (`create_task`, `remove_task`, `set_task_enabled`, `run_now`) that atomically perform the store write and the corresponding APScheduler job registration/deregistration in one place. `schedule_store` SHALL be the scheduler's private persistence layer: the tool layer MUST NOT import `schedule_store` directly (enforced by a dependency guardrail test). The module SHALL expose `cron_scheduler.current()` returning the running scheduler instance, registered at `start()` and cleared at `shutdown()`.

#### Scenario: Create registers the job immediately
- **WHEN** `CronScheduler.create_task(...)` is called on a running scheduler
- **THEN** the row is persisted AND `get_job(task_id)` returns a registered job, with no restart needed

#### Scenario: Remove deregisters the job immediately
- **WHEN** `CronScheduler.remove_task(task_id)` is called on a running scheduler
- **THEN** the row is deleted AND the APScheduler job is removed, so it never fires again

#### Scenario: Disable and re-enable toggle the live job
- **WHEN** `set_task_enabled(task_id, False)` then later `set_task_enabled(task_id, True)` are called
- **THEN** the job is deregistered then re-registered from the current store row, and `enabled` reflects each state

#### Scenario: Tool layer does not import the store
- **WHEN** the dependency guardrail test inspects `fleetent.tools`
- **THEN** no module under `tools/` imports `fleetent.schedule_store`

#### Scenario: current() lifecycle
- **WHEN** the scheduler completes `start()` / completes `shutdown()`
- **THEN** `cron_scheduler.current()` returns the instance / returns None

### Requirement: Fire-time revalidation against the store
Before executing, a fired job SHALL re-read its task row from the store by id. If the row is missing or `enabled=0`, the fire SHALL be skipped with a warning log and the stale job deregistered. The re-read row SHALL be used as the execution payload (not the dict captured at registration time). A `once` task that fires successfully SHALL be marked completed (`enabled=0`, `last_status="completed"`).

#### Scenario: Deleted task never fires
- **WHEN** a job fires whose store row was deleted by a writer that bypassed the facade
- **THEN** execution is skipped, a warning is logged, and the job is deregistered

#### Scenario: Disabled task never fires
- **WHEN** a job fires whose store row has `enabled=0`
- **THEN** execution is skipped and the job is deregistered

#### Scenario: Once task marked completed after firing
- **WHEN** a `once` task fires successfully
- **THEN** its row is updated to `enabled=0` and `last_status="completed"`, and it is not re-registered on next boot

## MODIFIED Requirements

### Requirement: schedule tool for managing scheduled tasks
A single `schedule` built-in tool SHALL let an agent manage scheduled tasks via an `action` parameter (`create`, `list`, `remove`, `run_now`, `pause`, `resume`). It SHALL have `risk_level="low"` and SHALL NOT require human approval. The tool SHALL perform all mutations through the running `CronScheduler` instance obtained via `cron_scheduler.current()` — never by writing `schedule_store` directly. `create` SHALL stamp the task's owner from the execution principal (`tool_context.principal.user_id`) when available, falling back to the `user_id` parameter only when no principal is present — the model-supplied parameter MUST NOT override an available principal. `create` SHALL return the new task's id; `pause`/`resume` SHALL toggle the task's `enabled` flag and deregister/register the APScheduler job accordingly; `run_now` SHALL fire the task immediately via a public scheduler method. When no scheduler is running (one-shot CLI run, or `scheduling.enabled=false`), mutations SHALL still persist to the store and the tool result SHALL state truthfully that the task takes effect when the agent service is running — the tool MUST NOT report the task as active.

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
