## ADDED Requirements

### Requirement: Four-layer resource metrics collection
A built-in lightweight collector SHALL periodically read four layers of metrics entirely within the internal network with no external dependency: (1) host resources (CPU, memory, disk usage and inode, load, network IO); (2) the fleetent process and sandbox containers (process CPU/memory/file handles, active sandbox container count, container OOM/timeout-kill counts); (3) dependency infrastructure (self-hosted PostgreSQL/Redis/Qdrant/RabbitMQ liveness, connection count, memory/disk usage, queue backlog); (4) application-layer metrics, which SHALL reuse the system health dashboard data and SHALL NOT be collected again here. The collection interval and metric retention period SHALL be configurable.

#### Scenario: Host metrics real-time and history (场景 86)
- **WHEN** an admin opens the resource monitoring dashboard while the collector is working
- **THEN** real-time host CPU/memory/disk/load levels are shown, and the view can switch to hourly/daily/weekly history curves

#### Scenario: Sandbox container OOM visible (场景 87)
- **WHEN** a sandbox code execution is OOM-killed for exceeding memory and the admin views the process + sandbox container layer
- **THEN** the active container count and the OOM/timeout-kill counters update and the event is observable in the monitoring view

#### Scenario: Dependency infrastructure liveness (场景 88)
- **WHEN** a self-hosted Redis instance stops responding and the collector runs its next cycle
- **THEN** monitoring marks Redis unavailable, and if a liveness alert rule is configured an alert is triggered

#### Scenario: Application-layer metrics reused, not re-collected
- **WHEN** the dashboard shows application-layer metrics (API error rate/latency, pending-approval backlog, active sessions, scheduled-task execution)
- **THEN** the values are read from the system health dashboard interface and the collector does not separately collect or store them

### Requirement: Collector self-failure is surfaced, never silently dropped
When the collector fails to read a layer (e.g. Docker unreachable, PostgreSQL connection refused), that target SHALL be marked "collection interrupted" in the UI and SHALL trigger an alert; data SHALL NOT be silently dropped.

#### Scenario: Collection interrupted raises alert
- **WHEN** the collector cannot reach the Docker daemon during a cycle
- **THEN** the sandbox/container target is marked "collection interrupted" in the dashboard and a collection-interrupted alert is raised rather than the gap being hidden

### Requirement: Real-time dashboard and history curves
The dashboard SHALL present one group of metric cards per layer with real-time levels plus optional time-range (hour/day/week) history curves, supporting multi-metric overlay comparison and filtering by host, container, or service instance.

#### Scenario: Filter and overlay metrics
- **WHEN** an admin selects a time range and filters by a specific host or container and overlays multiple metrics
- **THEN** the history curves render the selected metrics for the selected target over the selected range

### Requirement: Collection and storage stay within the internal network
Metric collection and storage SHALL complete entirely within the internal network with no dependency on any cloud-hosted service. Outbound traffic SHALL occur only when an admin explicitly configures a Webhook or email outbound channel.

#### Scenario: No cloud dependency, internal-only collection (场景 96)
- **WHEN** the platform runs resource monitoring and alerting in an isolated internal network
- **THEN** metric collection and time-series storage complete entirely on the internal network with no cloud-hosted service, and outbound traffic arises only from an admin-configured Webhook/email channel

### Requirement: Monitoring dashboard is read-only for viewers
A viewer SHALL be able to browse the monitoring dashboard and history (read-only). Login session resolution SHALL precede access; requests without a session SHALL be rejected with 401.

#### Scenario: Viewer browses dashboard
- **WHEN** a viewer opens the resource monitoring dashboard and history curves
- **THEN** the views render read-only and no rule-editing, ack, or silence controls are available to the viewer
