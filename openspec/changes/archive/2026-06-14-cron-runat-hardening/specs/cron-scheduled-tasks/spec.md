## MODIFIED Requirements

### Requirement: Dynamic tasks survive server restart
Tasks created via the `schedule` tool SHALL be persisted to the agent-side SQLite store and re-registered with APScheduler on every **agent process boot** (`agent_app.boot`), with `next_run_at` recomputed from the current time. Cron jobs SHALL NOT be loaded from YAML files. Re-registration MUST be bulkheaded per task: if registering one task raises (e.g. a malformed `run_at`), the scheduler SHALL log a warning, disable that task (`enabled=0`, so it is not re-loaded on the next boot), and skip it — it MUST NOT abort boot or prevent the remaining tasks from registering. A single bad row is a data problem, never an availability problem.

#### Scenario: Dynamic task re-registered after agent restart
- **WHEN** a task is created via `schedule_store.create()` and the agent process is restarted
- **THEN** the task is active again after `agent_app` starts its scheduler, with a freshly computed `next_run_at`

#### Scenario: Old cron YAML is not loaded
- **WHEN** a legacy cron YAML file exists
- **THEN** scheduler startup does not load static jobs from it

#### Scenario: One malformed task does not crash boot
- **WHEN** the store holds a `once` task whose `run_at` cannot be parsed (e.g. `'2026-06-14 08:07:19 UTC'` survived from an older writer) alongside valid tasks
- **THEN** scheduler start logs a warning for that task, disables it (`enabled=0`), registers all the valid tasks, and the scheduler starts normally — boot completes

## ADDED Requirements

### Requirement: Robust run_at parsing and write-time normalization
The one-shot `run_at` parser SHALL tolerate common non-strict ISO forms in addition to strict ISO-8601 and relative durations (`+30m`/`2h`): a trailing timezone-name suffix (` UTC`/` GMT`) MUST be normalized to a numeric offset before parsing, and a trailing `Z` MUST be accepted. When a `once` task is created via the `schedule` tool, the system SHALL normalize `run_at` through that same parser and persist the canonical ISO form (with explicit offset); an unparseable `run_at` MUST be rejected at create time with an explanatory error and MUST NOT be stored.

#### Scenario: run_at with UTC suffix parses
- **WHEN** `_parse_run_at("2026-06-14 08:07:19 UTC")` is evaluated
- **THEN** it resolves to the corresponding UTC datetime without raising

#### Scenario: strict ISO and relative durations still work
- **WHEN** `_parse_run_at("2026-06-14T08:07:19Z")` and `_parse_run_at("+30m")` are evaluated
- **THEN** both resolve correctly (absolute UTC; now + 30 minutes)

#### Scenario: create normalizes run_at to canonical ISO
- **WHEN** a `once` task is created via the `schedule` tool with `run_at="2026-06-14 08:07:19 UTC"`
- **THEN** the stored `run_at` is canonical ISO with an explicit offset (e.g. `2026-06-14T08:07:19+00:00`)

#### Scenario: create rejects an unparseable run_at
- **WHEN** a `once` task is created with a `run_at` the parser cannot resolve
- **THEN** the tool returns an explanatory error and no row is persisted
