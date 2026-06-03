# askit-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: AskIt tab
The admin console SHALL present an AskIt tab listing task series (`GET /admin/askit/series`) and recent tasks (`GET /admin/askit/tasks`).

#### Scenario: Admin sees askit series and tasks
- **WHEN** an admin opens the AskIt tab
- **THEN** series and tasks are listed via their endpoints

### Requirement: Run an AskIt task and view detail
The console SHALL let an admin run a task and open a task's detail.

#### Scenario: Run a task
- **WHEN** an admin submits a run
- **THEN** the console calls `POST /admin/askit/run` and the new task appears in the list

#### Scenario: View task detail
- **WHEN** an admin opens a listed task
- **THEN** the console calls `GET /admin/askit/tasks/{task_id}` and renders its detail
