# cron-scheduled-tasks Specification

## Purpose
Agent-owned scheduled tasks (cron/once/interval) persisted in an agent-side SQLite table, fired asynchronously by the in-process scheduler, managed via the unified `schedule` tool, with no platform dependency.

## Requirements

### Requirement: Scheduled task definition and persistence
The system SHALL store scheduled task definitions in an **agent-side** SQLite `scheduled_tasks` table whose schema is owned by `schedule_store` itself (idempotent `ensure_schema` with `CREATE TABLE IF NOT EXISTS`, named parameters; the database is resolved from `DATABASE_URL`, which the agent process points at its own data dir) — NOT by Alembic and NOT in the platform database (the management-DB table is dropped; `scheduled_tasks` becomes a pure agent-side table). Each task SHALL have: `id` (UUID), `name`, `schedule_kind` (`cron`/`once`/`interval`), the kind's schedule fields (`cron_expr` for cron, `run_at` for once, `interval_seconds` + optional `anchor` for interval), `timezone`, `user_id`, `message` (prompt text), optional `session_id`, `origin` (creation-context JSON), optional `deliver` (delivery-target JSON), `enabled` flag, `source` (`static`/`dynamic`/`tool`), `created_at`, and runtime-state columns `last_run_at`, `last_status`, `last_error`, `next_run_at`. The `agent_name` column SHALL NOT exist (one agent per process).

#### Scenario: Task created and persisted in agent DB
- **WHEN** `schedule_store.create(name=..., schedule_kind="cron", cron_expr="0 9 * * 1-5", user_id=..., message=...)` is called
- **THEN** a new row appears in the agent-side `scheduled_tasks` with a generated UUID id and `enabled=True`

#### Scenario: Schema self-created without Alembic
- **WHEN** `schedule_store.ensure_schema()` runs against a fresh agent database that has never run platform migrations
- **THEN** the `scheduled_tasks` table is created and CRUD succeeds without any platform dependency

#### Scenario: Tasks listed
- **WHEN** `schedule_store.list_tasks()` is called
- **THEN** all enabled rows are returned as a list of dicts including `schedule_kind`, `origin`, `deliver`, and the runtime-state columns

#### Scenario: Task deleted
- **WHEN** `schedule_store.delete(task_id)` is called with an existing id
- **THEN** the row is removed from `scheduled_tasks`

### Requirement: Dynamic tasks survive server restart
Tasks created via the `schedule` tool SHALL be persisted to the agent-side SQLite store and re-registered with APScheduler on every **agent process boot** (`agent_app.boot`), with `next_run_at` recomputed from the current time. Cron jobs SHALL NOT be loaded from YAML files.

#### Scenario: Dynamic task re-registered after agent restart
- **WHEN** a task is created via `schedule_store.create()` and the agent process is restarted
- **THEN** the task is active again after `agent_app` starts its scheduler, with a freshly computed `next_run_at`

#### Scenario: Old cron YAML is not loaded
- **WHEN** a legacy cron YAML file exists
- **THEN** scheduler startup does not load static jobs from it

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task's trigger (cron/once/interval) matches the current time, the scheduler SHALL call `agent_loop.run()` with the task's `message`, `user_id`, and (if configured) resolved agent system prompt and allowed tools. The trigger SHALL NOT block the scheduler event loop, and the run result SHALL be recorded in the observability trace.

#### Scenario: Agent run triggered on schedule
- **WHEN** a task's trigger fires
- **THEN** `agent_loop.run()` is invoked with the task's message and user_id without blocking the scheduler loop

#### Scenario: Run outcome recorded in runtime-state columns
- **WHEN** a triggered agent run completes or fails
- **THEN** the task's `last_run_at`, `last_status`, and (on failure) `last_error` are updated and the run is written to the eval trace

### Requirement: Scheduler global settings
The scheduler SHALL read its runtime settings from the **agent configuration** (`agent.yaml` `scheduling`), not from Platform settings.

#### Scenario: Scheduler disabled
- **WHEN** `agent.scheduling.enabled=false`
- **THEN** `agent_app` boot does not start APScheduler

#### Scenario: Default timezone is configured
- **WHEN** a persisted task does not define timezone
- **THEN** the scheduler uses `agent.scheduling.default_timezone`
### Requirement: Scheduled tasks are agent-owned with no platform dependency
Scheduled-task persistence and scheduling SHALL be entirely agent-runtime concerns. `schedule_store` and `cron_scheduler` MUST NOT `import fleetent.platform.*` and MUST NOT write to any platform table. An agent SHALL be able to create and fire scheduled tasks in an environment where the platform service is absent and the platform database / `scheduled_tasks` table do not exist.

#### Scenario: Create and fire without platform
- **WHEN** `fleetent agent run` is executed with no platform service and no platform database present
- **THEN** the `schedule` tool can create a task and the in-process scheduler fires it on time

#### Scenario: No reverse dependency on platform
- **WHEN** the agent-runtime scheduling modules are imported
- **THEN** they do not import `fleetent.platform.*` and do not access platform-owned tables

### Requirement: Schedule kinds cron, one-shot, and interval
The system SHALL support three schedule kinds mapped to APScheduler triggers: `cron` (5-field expression via `CronTrigger.from_crontab`), `once` (absolute timestamp or relative duration via `DateTrigger`), and `interval` (fixed period anchored from creation via `IntervalTrigger`).

#### Scenario: Cron schedule
- **WHEN** a task with `schedule_kind="cron"` and `cron_expr="0 9 * * 1-5"` is registered
- **THEN** it fires at 09:00 on weekdays in the task timezone

#### Scenario: One-shot schedule
- **WHEN** a task with `schedule_kind="once"` and `run_at` 30 minutes in the future is registered
- **THEN** it fires once at that time and is then marked `completed` (not re-run)

#### Scenario: Interval schedule
- **WHEN** a task with `schedule_kind="interval"` and `interval_seconds=5400` (90 minutes) is registered
- **THEN** it fires every 90 minutes anchored from its creation time

### Requirement: Missed-run handling on restart
The scheduler SHALL avoid burst-firing missed runs after the agent process was down by using APScheduler `misfire_grace_time`, `coalesce=True`, and a bounded `max_instances`. A `once` task whose `run_at` elapsed beyond the grace window while the process was down SHALL be marked `completed` without firing.

#### Scenario: Recurring task coalesces missed runs
- **WHEN** the agent process was down across several scheduled fire times and then boots
- **THEN** the recurring task fires at most once for the missed window (coalesced), not once per missed slot

#### Scenario: Expired one-shot is not fired late
- **WHEN** a `once` task's `run_at` passed beyond the grace window while the process was down
- **THEN** on boot it is marked `completed` and does not fire

### Requirement: schedule tool for managing scheduled tasks
A single `schedule` built-in tool SHALL let an agent manage scheduled tasks via an `action` parameter (`create`, `list`, `remove`, `run_now`, `pause`, `resume`). It SHALL have `risk_level="low"` and SHALL NOT require human approval. `create` SHALL return the new task's id; `pause`/`resume` SHALL toggle the task's `enabled` flag and deregister/register the APScheduler job accordingly; `run_now` SHALL fire the task immediately.

#### Scenario: Agent creates a schedule without approval
- **WHEN** an agent calls `schedule(action="create", schedule_kind="cron", cron_expr=..., message=...)`
- **THEN** a task is created with `source="tool"`, activated immediately, and its id is returned — with no approval gate

#### Scenario: Agent pauses and resumes a schedule
- **WHEN** an agent calls `schedule(action="pause", task_id=...)` then later `schedule(action="resume", task_id=...)`
- **THEN** the task's `enabled` flag is set to false then true, and the APScheduler job is deregistered then re-registered

#### Scenario: Agent removes a schedule
- **WHEN** an agent calls `schedule(action="remove", task_id=...)` with a valid id
- **THEN** the task is deleted from `scheduled_tasks` and deregistered from the scheduler

#### Scenario: run_now fires immediately
- **WHEN** an agent calls `schedule(action="run_now", task_id=...)`
- **THEN** the task fires once immediately without altering its normal schedule

#### Scenario: Removing non-existent task returns error message
- **WHEN** an agent calls `schedule(action="remove", task_id="nonexistent")`
- **THEN** the tool returns an error string without raising an exception
