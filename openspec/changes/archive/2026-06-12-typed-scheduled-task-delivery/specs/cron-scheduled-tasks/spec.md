## ADDED Requirements

### Requirement: Delivery contract — only designated content is ever broadcast

The scheduler SHALL deliver to a task's target only content **explicitly designated as the
notification**: the frozen `notify_text` of a `notify` task, or the final reply of a
`generate` task produced under the fired-run delivery statement. The scheduler SHALL NOT
broadcast free-form conversational replies: an `action` task's final reply MUST NOT be
delivered to the task target — it is recorded as the run report (trace + task runtime
columns) only. Fired runs have no interlocutor; the `generate` fired-run context SHALL
state the delivery target, require the reply to contain only the notification body,
forbid questions/operator-facing commentary, and document `[SILENT]` as the skip sentinel.

#### Scenario: Action task reply is not broadcast

- **WHEN** an `action` task fires and the agent's final reply is a run summary
- **THEN** the scheduler does not send that reply to the task's target; it is recorded in
  the run trace and task runtime columns only

#### Scenario: Generate run receives the delivery statement

- **WHEN** a `generate` task fires
- **THEN** the messages given to `agent_loop.run` include the scheduled-run statement
  naming the delivery target, restricting the reply to the notification body, and
  documenting `[SILENT]`

#### Scenario: Diagnostic prose cannot reach the channel as a "notification"

- **WHEN** a fired run fails at its intent and the agent's reply is an error explanation
- **THEN** for `action` tasks nothing is broadcast, and for `generate`/`notify` tasks the
  task's `last_status` is `error` — a delivered-but-wrong-content run MUST NOT be
  recorded as `ok`

### Requirement: Notify copy is finalized at creation time

For `notify` tasks the notification copy SHALL be produced **once, at creation time**, in
the creating conversation: the agent polishes the user's raw phrasing into the final
copy, echoes it back for confirmation, and stores the frozen result in `notify_text`.
Firing a `notify` task SHALL NOT run the agent and SHALL NOT rewrite the copy: the
scheduler sends `notify_text` verbatim via the fire-time connector snapshot. Content
that requires fire-time information (dates, fresh data, conditions) SHALL be created as
a `generate` or `action` task instead — the deciding question is whether the message
content needs information only known at send time.

#### Scenario: Rough phrasing is polished once and frozen

- **WHEN** a user asks the agent to schedule a daily reminder using rough phrasing
- **THEN** the agent stores a polished final copy in `notify_text` after echoing it for
  confirmation, and every subsequent fire sends exactly that frozen copy

#### Scenario: Notify fire is deterministic and agent-free

- **WHEN** a `notify` task fires
- **THEN** the scheduler sends `notify_text` verbatim to the resolved target without
  invoking `agent_loop.run`, and `last_status` reflects the delivery outcome

#### Scenario: Fire-time-dependent content is steered away from notify

- **WHEN** a user asks to schedule a reminder whose content includes "today's todo list"
- **THEN** the task is created as `generate` (not `notify`), because the content needs
  send-time information

## MODIFIED Requirements

### Requirement: Scheduled task definition and persistence
The system SHALL store scheduled task definitions in an **agent-side** SQLite `scheduled_tasks` table whose schema is owned by the per-agent `agent_state.db` unified embedded forward-only migrations (`AGENT_STATE_MIGRATIONS`, with `PRAGMA user_version` + migrate-on-open), NOT by `schedule_store` self-init and NOT by Alembic and NOT in the platform database. `schedule_store` SHALL access the table through a database injected via `schedule_store.set_state_db(db)`; `schedule_store` SHALL NOT expose an `ensure_schema()` entry point and SHALL NOT resolve `DATABASE_URL` to self-connect. All SQL SHALL use named parameters. Each task SHALL have: `id` (UUID), `name`, `schedule_kind` (`cron`/`once`/`interval`), the kind's schedule fields, `timezone`, `user_id`, `message` (prompt text for `generate`/`action`; MAY hold the user's original phrasing for `notify`), **`task_type` (`notify`/`generate`/`action`, default `generate`)**, **`notify_text` (frozen notification copy, required for `notify`)**, optional `session_id`, `origin` (creation-context JSON), optional `deliver` (delivery-target JSON), `enabled` flag, `source` (`static`/`dynamic`/`tool`), `created_at`, and runtime-state columns `last_run_at`, `last_status`, `last_error`, `next_run_at`. The `agent_name` column SHALL NOT exist. The store SHALL validate per type: `notify` requires `notify_text` and a resolvable delivery target; `generate`/`action` require `message`.

#### Scenario: Notify task persisted with frozen copy

- **WHEN** `schedule_store.create(task_type="notify", notify_text="📅 晨会提醒：9:00 准时开始", ...)` is called
- **THEN** the row persists with `task_type="notify"` and the frozen copy, and creating a `notify` task without `notify_text` fails validation

#### Scenario: Legacy default keeps prior semantics

- **WHEN** a task is created without `task_type` (older caller)
- **THEN** it persists as `generate`, the closest equivalent of the previous run-and-deliver behavior

#### Scenario: Schema upgraded by embedded migrations

- **WHEN** an existing `agent_state.db` is opened by the new code version
- **THEN** the new `task_type`/`notify_text` columns exist via the appended `AGENT_STATE_MIGRATIONS` version, with existing rows defaulted to `generate`

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task's trigger (cron/once/interval) matches the current time, the scheduler SHALL fire **according to the task's `task_type`**: `notify` sends `notify_text` verbatim via the fire-time connector snapshot **without invoking `agent_loop.run`**; `generate` and `action` call `agent_loop.run()` with the task's `message`, `user_id`, resolved agent context, the fire-time `outbound_connectors` snapshot, and (for `generate`) the scheduled-run delivery statement. The trigger SHALL NOT block the scheduler event loop, and the run result SHALL be recorded in the observability trace. `last_status` SHALL reflect the **task intent** outcome per type — notify: delivery outcome; generate: run + delivery outcome; action: run outcome — never merely "the delivery API call succeeded".

#### Scenario: Notify fire bypasses the agent

- **WHEN** a `notify` task's trigger fires
- **THEN** the scheduler sends `notify_text` to the resolved target without calling `agent_loop.run`

#### Scenario: Generate/action runs receive fire-time connectors

- **WHEN** a `generate` or `action` task's trigger fires
- **THEN** `agent_loop.run()` is invoked with `outbound_connectors` resolved from the connector registry at fire time, without blocking the scheduler loop

#### Scenario: Intent-level status recorded

- **WHEN** a fired task fails at its intent (notify delivery fails; generate run or delivery fails; action run fails)
- **THEN** `last_run_at`/`last_status`/`last_error` record `error` with the precise cause, and the run is written to the eval trace

### Requirement: schedule tool for managing scheduled tasks
A single `schedule` built-in tool SHALL let an agent manage scheduled tasks via an `action` parameter (`create`, `list`, `remove`, `run_now`, `pause`, `resume`). It SHALL have `risk_level="low"` and SHALL NOT require human approval. The tool SHALL perform all mutations through the running `CronScheduler` instance obtained via `cron_scheduler.current()` — never by writing `schedule_store` directly. `create` SHALL accept `task_type` (default `generate`) and `notify_text`, enforcing the per-type validation (notify requires `notify_text` + delivery target; generate/action require `message`), and its tool description SHALL carry the type-deciding question ("does the message content need information only known at send time?") plus the creation-time finalize-and-confirm flow for notify copy. `create` SHALL stamp the task's owner from the execution principal (`tool_context.principal.user_id`) when available, falling back to the `user_id` parameter only when no principal is present. `create` SHALL return the new task's id; `pause`/`resume` SHALL toggle `enabled` and deregister/register the APScheduler job; `run_now` SHALL fire immediately via a public scheduler method. When no scheduler is running, mutations SHALL still persist and the tool result SHALL state truthfully that the task takes effect when the agent service is running.

#### Scenario: Agent creates a notify task with frozen copy

- **WHEN** an agent calls `schedule(action="create", task_type="notify", notify_text="📅 晨会提醒：9:00 准时开始", schedule_kind="cron", cron_expr="0 9 * * 1-5")`
- **THEN** the task is created with `task_type="notify"`, fires agent-free, and its id is returned

#### Scenario: Notify creation without copy is rejected

- **WHEN** an agent calls `schedule(action="create", task_type="notify")` without `notify_text`
- **THEN** the tool returns a validation error string without raising

#### Scenario: Untyped create stays compatible

- **WHEN** an agent calls `schedule(action="create", message=..., cron_expr=...)` without `task_type`
- **THEN** a `generate` task is created, preserving the prior call shape
