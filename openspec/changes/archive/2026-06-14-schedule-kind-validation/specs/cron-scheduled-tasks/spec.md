## MODIFIED Requirements

### Requirement: Schedule kinds cron, one-shot, and interval
The system SHALL support three schedule kinds mapped to APScheduler triggers: `cron` (5-field expression via `CronTrigger.from_crontab`), `once` (absolute timestamp or relative duration via `DateTrigger`), and `interval` (fixed period anchored from creation via `IntervalTrigger`). `schedule_kind` MUST be validated at task creation: a value outside `{cron, once, interval}` MUST be rejected with a clear `ValueError` (e.g. `invalid schedule_kind: 'run_at' (cron/once/interval)`) and MUST NOT be persisted — so an invalid kind can never reach registration (where a non-matching kind would fall through to the cron branch and crash on a missing cron expression). As a forgiving normalization for the common model confusion of passing the parameter name as the kind, `schedule_kind="run_at"` MUST be treated as `"once"` at creation (then the one-shot `run_at` normalization applies).

#### Scenario: Cron schedule
- **WHEN** a task with `schedule_kind="cron"` and `cron_expr="0 9 * * 1-5"` is registered
- **THEN** it fires at 09:00 on weekdays in the task timezone

#### Scenario: One-shot schedule
- **WHEN** a task with `schedule_kind="once"` and `run_at` 30 minutes in the future is registered
- **THEN** it fires once at that time and is then marked `completed` (not re-run)

#### Scenario: Interval schedule
- **WHEN** a task with `schedule_kind="interval"` and `interval_seconds=5400` (90 minutes) is registered
- **THEN** it fires every 90 minutes anchored from its creation time

#### Scenario: run_at is aliased to once
- **WHEN** a one-shot task is created with `schedule_kind="run_at"` and a valid `run_at` time
- **THEN** it is normalized to `schedule_kind="once"`, persisted as a one-shot, and fires at `run_at` (no registration failure)

#### Scenario: invalid schedule_kind is rejected at creation
- **WHEN** a task is created with a `schedule_kind` that is not one of `cron`/`once`/`interval` (and not the `run_at` alias)
- **THEN** creation raises a clear `ValueError` naming the allowed kinds and persists no row; the `schedule` tool surfaces it as an explanatory error so the agent can retry with a valid kind
