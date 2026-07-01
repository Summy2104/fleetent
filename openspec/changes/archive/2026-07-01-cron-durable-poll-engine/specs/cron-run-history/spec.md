## ADDED Requirements

### Requirement: Per-run history persistence
The scheduler SHALL persist a **row per fire occurrence** in an agent-owned `scheduled_task_runs` table (agent_state.db, created via a forward-only embedded migration). Each row SHALL record at least: the task id, the fire time, a `status` of `ok` / `error` / `missed` / `skipped`, the **agent error and the delivery error as separate fields** (a run can produce output yet fail delivery), the run duration, and the task kind/type at fire time. The history write SHALL be best-effort on the fire path — a history-write failure SHALL be logged and MUST NOT crash the scheduler or change the fire outcome. `scheduled_task_runs` SHALL be agent-owned: it MUST NOT be a platform table and its writers MUST NOT `import fleetent.platform.*`.

#### Scenario: Successful run appended to history
- **WHEN** a task fires and both the run and delivery succeed
- **THEN** a `scheduled_task_runs` row is appended with `status="ok"`, the fire time, duration, and null agent/delivery errors

#### Scenario: Agent error and delivery error recorded separately
- **WHEN** a `generate` task's run produces output but delivery to the target fails
- **THEN** the history row records the delivery error in the delivery-error field with the agent-error field null (and `status="error"`), distinguishing "the agent failed" from "delivery failed"

#### Scenario: History write failure never breaks a fire
- **WHEN** appending a run-history row raises (e.g. a transient DB error)
- **THEN** the failure is logged and the fire still completes and delivers; the scheduler does not crash

#### Scenario: History table is agent-owned
- **WHEN** the run-history persistence module is imported
- **THEN** it does not import `fleetent.platform.*` and writes only to the agent-owned state database

### Requirement: Bounded run-history retention
The scheduler SHALL bound run-history growth by retaining at most the most recent N runs per task (N configurable with a safe default); older rows for that task SHALL be pruned. Deleting a task SHALL remove its run-history rows.

#### Scenario: Oldest runs pruned beyond the retention bound
- **WHEN** a task accumulates more than the retention bound of run rows
- **THEN** only the most recent N rows for that task are kept; older rows are pruned

#### Scenario: Deleting a task removes its history
- **WHEN** a task is deleted
- **THEN** its `scheduled_task_runs` rows are removed (no orphaned history)

### Requirement: schedule tool history action
The agent-facing `schedule` tool SHALL expose a `history` action that returns the most recent runs for a given `task_id` (fire time, status, agent/delivery error, duration), so the recurring behavior of a task is observable from the agent (Slack/chat) without any admin UI. An unknown `task_id` SHALL return a clear error string, not raise.

#### Scenario: History action returns recent runs
- **WHEN** the `schedule` tool is called with `action="history"` and a valid `task_id`
- **THEN** it returns the most recent runs for that task including each run's fire time, status, and any agent/delivery error

#### Scenario: History for an unknown task
- **WHEN** `action="history"` is called with a `task_id` that does not exist
- **THEN** the tool returns a clear error string (e.g. `error: task <id> not found`) rather than raising
