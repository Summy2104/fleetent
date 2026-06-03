# alert-lifecycle Specification

## Purpose
TBD - created by archiving change 2026-06-02-resource-monitoring-alerting. Update Purpose after archive.
## Requirements
### Requirement: Alert lifecycle state machine
Each alert SHALL follow a state machine: firing → notified → ack → resolved. A firing alert SHALL transition to notified after multi-channel notification, to ack when an admin confirms it, and to resolved when the metric returns within threshold. From notified an alert MAY transition directly to resolved on metric recovery, or to silenced under a maintenance window or manual silence. State transitions SHALL be driven by a single point and SHALL NOT use free-form status strings.

#### Scenario: Ack then recovery (场景 91)
- **WHEN** an admin clicks acknowledge on a firing alert and assigns a handler, and the metric then returns within threshold
- **THEN** the alert transitions ack → resolved, a recovery notification is sent, and the whole sequence is recorded in alert history

### Requirement: Critical alert escalation when unacknowledged
A critical alert that has been notified but not acknowledged within the configured escalation wait time SHALL escalate per the escalation policy to higher-priority channels or more recipients. The escalation action SHALL be written to the audit log.

#### Scenario: Unacknowledged critical escalates (场景 90)
- **WHEN** a critical alert has been notified and no one acknowledges it within N minutes and escalation is configured
- **THEN** the alert escalates per policy to higher-priority channels / more recipients, and the escalation action is written to the audit log

### Requirement: Deduplication, aggregation, grouping, and inhibition
Repeated hits of the same rule on the same target SHALL be deduplicated/aggregated into a single active alert rather than flooding. During an alert storm, alerts SHALL be grouped by target/severity. Inhibition rules SHALL be supported, including a built-in rule that a host-down/unreachable condition inhibits secondary alerts for the containers and processes on that host.

#### Scenario: Dedup and host-down inhibition (场景 92)
- **WHEN** a host goes down and its 10 containers simultaneously become unreachable
- **THEN** repeated hits of the same rule are deduplicated into a single active alert, and the host-down alert inhibits the secondary alerts of its containers so they do not flood

### Requirement: Maintenance window silencing
An admin SHALL be able to define a maintenance window for a target or globally. Alerts that hit a rule within the window SHALL be recorded only and SHALL NOT be notified; normal notification SHALL resume after the window ends.

#### Scenario: Window silences notification (场景 93)
- **WHEN** an admin sets a 22:00–23:00 maintenance window for a host and that host's metric hits an alert rule within the window
- **THEN** the alert is recorded only with no notification sent, and normal notification resumes after the window ends

### Requirement: Alert center search, snapshot, and audit
The alert center SHALL allow searching all historical alerts filtered by target, severity, status, and time. Each alert SHALL be associated with the metric snapshot at trigger time and its handling record. Rule create/update/delete, ack, and silence actions SHALL be written to the audit log.

#### Scenario: Search history with snapshot and handling record
- **WHEN** an admin searches the alert center by target, severity, status, and time range
- **THEN** matching historical alerts are listed, each linked to its trigger-time metric snapshot and handling record (ack handler, silence, escalation, notification results)

#### Scenario: Ack and silence are audited
- **WHEN** an admin acknowledges or silences an alert
- **THEN** the action is written to the audit log with actor, action, target, and a masked detail

#### Scenario: Alert center read-only for viewers (场景 95)
- **WHEN** a viewer opens the alert center
- **THEN** they may browse history and detail but cannot ack, silence, or assign a handler; those actions are hidden or return 403

