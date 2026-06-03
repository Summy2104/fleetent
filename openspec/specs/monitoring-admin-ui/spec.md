# monitoring-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Monitoring tab
The admin console SHALL present a Monitoring tab showing resource metrics from `GET /admin/monitoring/metrics`.

#### Scenario: Admin sees metrics
- **WHEN** an admin opens the Monitoring tab
- **THEN** current resource metrics are rendered

### Requirement: Alert rules management
The console SHALL list alert rules and let an admin create, disable, and delete a rule. Write controls SHALL be admin-only.

#### Scenario: Create an alert rule
- **WHEN** an admin creates a rule
- **THEN** the console calls `POST /admin/alerts/rules` and the rule appears

#### Scenario: Disable a rule
- **WHEN** an admin disables a listed rule
- **THEN** the console calls `POST /admin/alerts/rules/{rule_id}/disable`

### Requirement: Alert handling
The console SHALL list active alerts and let an admin acknowledge, silence, and set a maintenance window.

#### Scenario: Acknowledge an alert
- **WHEN** an admin acknowledges a listed alert
- **THEN** the console calls `POST /admin/alerts/{alert_id}/ack` and the alert reflects acked
