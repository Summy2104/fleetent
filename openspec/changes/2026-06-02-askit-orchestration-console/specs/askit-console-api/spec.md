## ADDED Requirements

### Requirement: Series-grouped console layout
The askit orchestration console SHALL present the eight command series as separate grouped cards, each listing that series' triggerable operations, last-run status, and duration. The console SHALL only expose the observable behavior of each series' commands and SHALL NOT redefine askit semantics.

#### Scenario: Console groups operations by series
- **WHEN** an admin opens the askit orchestration console and the page loads
- **THEN** eight series cards are shown (Authoring / Build & Validate / Deploy / Skill Deps / Override Flow / Cron / Env & MCP / Migrations)
- **AND** each card lists its triggerable operations with last-run status and duration

### Requirement: Asynchronous task with streaming logs and history
Each series operation SHALL execute as one asynchronous task that streams askit stdout/stderr to the UI in real time, persists the output for later replay, and on completion shows the exit code and (on failure) an error summary. Every run SHALL be written to audit and history.

#### Scenario: Trigger build streams live logs
- **WHEN** an admin clicks `build` under the Build & Validate series and the task runs asynchronously
- **THEN** the UI streams askit stdout/stderr in real time
- **AND** on completion the exit code and (if failed) an error summary are shown
- **AND** the run is recorded in audit and history

#### Scenario: History replay
- **WHEN** an admin opens a past task from history
- **THEN** its persisted stdout/stderr, exit code, parameters (redacted), and produced artifact / PR links are shown

### Requirement: Deploy check gate
When the hard gate is enabled, the Deploy series SHALL block a `deploy` while the most recent `check` reports drift (not green), prompting the operator to pass `check` first.

#### Scenario: check not green blocks deploy
- **WHEN** the hard gate is enabled and the latest `check` detected drift, and an admin clicks `deploy`
- **THEN** the deploy is blocked with a prompt to pass `check` first
- **AND** after `check` passes, deploy can be initiated again

### Requirement: Dry-run preview for deploy
The Deploy series SHALL support a `--dry-run` toggle that outputs the planned file changes without writing any artifact. Disabling dry-run for an actual deploy SHALL require a second confirmation.

#### Scenario: Deploy dry-run writes nothing
- **WHEN** an admin selects a target platform, checks `--dry-run`, and executes
- **THEN** only the planned file changes are output and no artifact is written
- **AND** unchecking `--dry-run` requires a second confirmation before an actual deploy

### Requirement: Override-flow review with diff and Promote/Discard/Skip
The Override Flow series SHALL present each pending override as a diff and let the admin choose Promote / Discard / Skip. Promoted items SHALL produce a PR via `promote`, with the PR link visible in the UI, and the decision SHALL be audited.

#### Scenario: Review overrides with P/D/S
- **WHEN** runtime overrides exist and an admin clicks `review` and inspects each one
- **THEN** each override is shown as a diff and the admin can choose Promote / Discard / Skip
- **AND** Promoted items produce a PR via `promote`, the PR link is visible in the UI, and the decision is audited

### Requirement: Cron declared-vs-installed diff
The Cron series SHALL highlight added / missing / changed tasks between the declared and installed state, and SHALL require a second confirmation before `install` / `remove`.

#### Scenario: Cron diff highlights differences
- **WHEN** the declared cron differs from the installed cron and an admin clicks `diff`
- **THEN** the UI highlights added / missing / changed tasks
- **AND** executing `install` / `remove` requires a second confirmation

### Requirement: Redacted environment diagnostics
The Env & MCP series SHALL render diagnostic conclusions as a red / yellow / green list and SHALL redact sensitive variable values so they never appear in plaintext in the UI or logs.

#### Scenario: env doctor redacts secrets
- **WHEN** an admin clicks `env doctor` and the diagnostic completes
- **THEN** the conclusions render as a red / yellow / green list
- **AND** the involved sensitive variable values are redacted and never shown in plaintext in the UI or logs

### Requirement: Migrations default to dry-run
The Migrations series SHALL run each migration as dry-run by default, showing the files that would change without writing, and SHALL only write after a second confirmation; the write action SHALL be audited.

#### Scenario: Migration first runs dry-run
- **WHEN** an admin clicks a migration command for the first time
- **THEN** it runs as dry-run, showing the files that would change, writing nothing
- **AND** only after a second confirmation does it actually write, and the write is audited

### Requirement: Role-based access in the console
viewer SHALL be able to trigger read-only operations (such as lint / check / diff / doctor) and view logs and history, while Authoring / Deploy / Skill Deps / Migrations and other write operations SHALL be hidden or return 403 for viewer. High-risk series (Deploy / Migrations / promote) SHALL require a second confirmation plus 2FA.

#### Scenario: viewer is read-only
- **WHEN** a viewer is logged into the console and inspects the series
- **THEN** the viewer can trigger read-only operations (lint / check / diff / various doctor) and view logs and history
- **BUT** Authoring / Deploy / Skill Deps / Migrations write buttons are hidden or return 403

#### Scenario: High-risk series requires 2FA
- **WHEN** an admin triggers a Deploy / Migrations / promote operation
- **THEN** a second confirmation plus a current 2FA check is required before the operation runs

### Requirement: Per-workspace serial write queue
Write operations (build / deploy / override promote / migrate) on the same workspace SHALL be serialized, never executed concurrently, with queued status shown in the UI. Read-only operations MAY run concurrently.

#### Scenario: Same-workspace writes serialize
- **WHEN** a `build` task is running and an admin triggers a `deploy` on the same workspace
- **THEN** the later write operation queues until the former completes and does not run concurrently
- **AND** the UI shows its queued status

### Requirement: Subprocess invocation with pinned askit version
The console SHALL invoke askit as a subprocess of the pinned in-image askit CLI version (not as a linked library), with a controlled argument allowlist, and SHALL record the askit version in the task audit.

#### Scenario: Audit records askit version and parameters
- **WHEN** any series operation runs
- **THEN** the audit entry records the initiator, series, command, redacted parameters, exit code, produced artifact / PR links, and the pinned askit version
