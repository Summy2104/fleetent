## ADDED Requirements

### Requirement: Visual task_type routing order edit
For each task_type (e.g. `default` / `cheap` / `code`), an admin SHALL manage the provider list whose order is the fallback priority. The admin SHALL be able to reorder (drag), add, and remove providers under a task_type. Saving SHALL take effect via the config write boundary, and changing a production task_type route SHALL be audited. Runtime fallback semantics remain owned by model-router.

#### Scenario: Reordering changes fallback priority
- **WHEN** task_type "default" has provider list [A, B] and an admin reorders it to [B, A] and saves
- **THEN** at runtime "default" prefers B and falls back to A when B is unavailable (fallback semantics per model-router), and the reorder is written to the audit log

### Requirement: Unknown task_type fallback is shown
The console SHALL clearly indicate that a task_type with no configured providers falls back to `default` at runtime (semantics per model-router) without raising an error. This surface only renders the fallback rule and does not recompute routing.

#### Scenario: Undefined task_type shows fallback notice
- **WHEN** no provider is configured for "rare_task" and an admin views the routing console
- **THEN** the UI states that the undefined task_type falls back to "default" at runtime and does not report an error

### Requirement: Fallback chain preview
An admin SHALL be able to select a task_type and view its full fallback order, and simulate the "primary unavailable" step-by-step fallback path (aligned with model-router fallback traversal). The preview is a read-only demonstration and SHALL NOT issue real model calls or trigger real fallback.

#### Scenario: Preview shows ordered chain without real calls
- **WHEN** an admin previews the fallback chain for a task_type
- **THEN** the full ordered chain `[primary, ...fallbacks]` is shown and the simulated step-by-step degradation is rendered without issuing any real model call

### Requirement: Health probe status visibility
The console SHALL display the model-router health-probe cache results: which provider is marked temporarily unavailable after consecutive failures, is skipped during fallback, and its recovery time. Status is judged by model-router; this surface only renders it.

#### Scenario: Skipped provider visible with recovery time
- **WHEN** model-router has marked a provider temporarily unavailable after consecutive failures
- **THEN** the console shows that provider as unavailable / skipped-on-fallback with its recovery time, sourced from the model-router health-probe cache

### Requirement: Routing edits are role-gated
Reordering, adding, or removing providers in a task_type route SHALL be restricted to `admin` / `built_in_admin`. A `viewer` SHALL only view routing order, fallback preview results, and health status.

#### Scenario: Viewer cannot edit routing order
- **WHEN** a viewer attempts to reorder or change a task_type's provider list
- **THEN** the controls are hidden or the request returns 403
