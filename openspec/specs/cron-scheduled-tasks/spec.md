# cron-scheduled-tasks Specification

## Purpose
TBD - created by archiving change cron-scheduled-tasks. Update Purpose after archive.
## Requirements
### Requirement: Scheduled task definition and persistence
The system SHALL store scheduled task definitions in a SQLite `scheduled_tasks` table. Each task SHALL have: `id` (UUID), `name`, `cron_expr` (5-field cron expression), `timezone`, `user_id`, optional `agent_name`, `message` (prompt text), `enabled` flag, `source` (`static`/`dynamic`/`tool`), and `created_at`.

#### Scenario: Task created and persisted
- **WHEN** `schedule_store.create(name=..., cron_expr="0 9 * * 1-5", user_id=..., message=...)` is called
- **THEN** a new row appears in `scheduled_tasks` with a generated UUID id and `enabled=True`

#### Scenario: Tasks listed
- **WHEN** `schedule_store.list_tasks()` is called
- **THEN** all rows in `scheduled_tasks` are returned as a list of dicts

#### Scenario: Task deleted
- **WHEN** `schedule_store.delete(task_id)` is called with an existing id
- **THEN** the row is removed from `scheduled_tasks`

### Requirement: Static tasks loaded from config/cron.yaml
At server startup, the system SHALL load task definitions from `config/cron.yaml` and register them with the scheduler. If the file does not exist, startup SHALL proceed without error. Static tasks are identified by `source="static"`.

#### Scenario: Valid config loaded
- **WHEN** `config/cron.yaml` exists with at least one job entry
- **THEN** the job is registered with APScheduler using its cron expression and timezone

#### Scenario: Missing config file is silently skipped
- **WHEN** `config/cron.yaml` does not exist
- **THEN** the server starts without error and no static jobs are scheduled

### Requirement: Dynamic tasks survive server restart
Tasks created via admin CLI or the `schedule_task` tool SHALL be persisted to SQLite and re-registered with APScheduler on every server startup.

#### Scenario: Dynamic task re-registered after restart
- **WHEN** a task is created via `schedule_store.create()` and the scheduler is restarted
- **THEN** the task is active again after calling `cron_scheduler.start()`

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task's cron expression matches the current time, the scheduler SHALL call `agent_loop.run()` with the task's `message`, `user_id`, and (if configured) resolved agent system prompt and allowed tools. The trigger SHALL NOT block the scheduler event loop.

#### Scenario: Agent run triggered on schedule
- **WHEN** a task's cron expression fires
- **THEN** `agent_loop.run()` is called with the task's message and user_id as an asyncio background task

#### Scenario: Agent run result recorded in trace
- **WHEN** a cron-triggered agent run completes
- **THEN** the result is written to the eval trace (same as HTTP-triggered runs)

### Requirement: schedule_task tool for dynamic scheduling
The `schedule_task` built-in tool SHALL allow an agent to create a new scheduled task. It SHALL have `risk_level="high"` to require human approval. On success it SHALL return the new task's id.

#### Scenario: Agent creates a schedule
- **WHEN** an agent calls `schedule_task(name=..., cron_expr=..., message=..., user_id=...)`
- **AND** the human approves the action
- **THEN** a new task is created in `scheduled_tasks` with `source="tool"` and activated immediately

### Requirement: cancel_task tool for removing schedules
The `cancel_task` built-in tool SHALL allow an agent to cancel a scheduled task by id. It SHALL have `risk_level="medium"`.

#### Scenario: Agent cancels a schedule
- **WHEN** an agent calls `cancel_task(task_id=...)` with a valid id
- **AND** the human approves the action
- **THEN** the task is removed from `scheduled_tasks` and deregistered from the scheduler

#### Scenario: Cancelling non-existent task returns error message
- **WHEN** an agent calls `cancel_task(task_id="nonexistent")`
- **THEN** the tool returns an error string without raising an exception

### Requirement: Admin CLI commands for schedule management
The admin CLI SHALL provide `list-schedules`, `add-schedule`, and `remove-schedule` commands for operator management of scheduled tasks.

#### Scenario: list-schedules with no tasks
- **WHEN** `mini-agent-admin list-schedules` is run with no tasks defined
- **THEN** output contains "No scheduled tasks"

#### Scenario: add-schedule creates a persisted task
- **WHEN** `mini-agent-admin add-schedule --name "Daily" --cron "0 9 * * *" --user-id <id> --message "Hello"` is run
- **THEN** exit code is 0 and a new task id is printed

#### Scenario: remove-schedule deletes a task
- **WHEN** `mini-agent-admin remove-schedule --task-id <id>` is run with a valid id
- **THEN** exit code is 0 and the task no longer appears in list-schedules

