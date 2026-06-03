## ADDED Requirements

### Requirement: Providers management tab
The admin console SHALL present a Model Providers tab listing each provider with masked credentials and a health indicator. Write controls SHALL be admin-only.

#### Scenario: Admin sees providers list
- **WHEN** an admin opens the Providers tab
- **THEN** each provider is listed via `GET /admin/providers` with credential fields masked

#### Scenario: Viewer cannot mutate providers
- **WHEN** a viewer opens the Providers tab
- **THEN** create / edit / delete / connectivity-test / pricing controls are hidden

### Requirement: Provider CRUD and connectivity
The console SHALL let an admin create, edit, delete a provider, run a connectivity test, and set pricing, calling the matching `/admin/providers` endpoints.

#### Scenario: Connectivity test
- **WHEN** an admin runs a connectivity test on a provider
- **THEN** the console calls `POST /admin/providers/{id}/connectivity-test` and shows the result

### Requirement: Task-type routing
The console SHALL show the task_type → provider route table and let an admin update a route (with preview).

#### Scenario: Update a route
- **WHEN** an admin sets a new provider for a task_type
- **THEN** the console calls `PUT /admin/providers/routes/{task_type}` and the table reflects it
