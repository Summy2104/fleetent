## MODIFIED Requirements

### Requirement: Dynamic tasks survive server restart
Tasks created via admin CLI or the `schedule_task` tool SHALL be persisted to SQLite and re-registered with
APScheduler on every server startup. Cron jobs SHALL NOT be loaded from YAML files.

#### Scenario: Dynamic task re-registered after restart
- **WHEN** a task is created via `schedule_store.create()` and the scheduler is restarted
- **THEN** the task is active again after calling `cron_scheduler.start()`

#### Scenario: Old cron YAML is not loaded
- **WHEN** `config/cron.yaml` exists
- **THEN** scheduler startup fails fast instead of loading static jobs

## REMOVED Requirements

### Requirement: Static tasks loaded from config/cron.yaml
At server startup, the system SHALL load task definitions from `config/cron.yaml` and register them with the scheduler. If the file does not exist, startup SHALL proceed without error. Static tasks are identified by `source="static"`.

#### Scenario: Valid config loaded
- **WHEN** `config/cron.yaml` exists with at least one job entry
- **THEN** the job is registered with APScheduler using its cron expression and timezone

#### Scenario: Missing config file is silently skipped
- **WHEN** `config/cron.yaml` does not exist
- **THEN** the server starts without error and no static jobs are scheduled

## ADDED Requirements

### Requirement: Scheduler global settings
The scheduler SHALL read deployment-level runtime settings from `config/settings.yaml`.

#### Scenario: Scheduler disabled
- **WHEN** `scheduling.enabled=false`
- **THEN** server startup does not start APScheduler

#### Scenario: Default timezone is configured
- **WHEN** a persisted task does not define timezone
- **THEN** scheduler uses `scheduling.default_timezone`
