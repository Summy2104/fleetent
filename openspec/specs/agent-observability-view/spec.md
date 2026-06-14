# agent-observability-view Specification

## Purpose
TBD - created by archiving change 2026-06-02-agent-management-console. Update Purpose after archive.
## Requirements
### Requirement: Per-agent aggregated observability view
The system SHALL provide a per-agent observability view aggregated by `agent_name` from the observability traces. The view SHALL surface, for a given time window: call count, token/cost usage, error rate, average latency, permission_gate trigger count and approval rate, and a recent-session list. The view SHALL only aggregate existing observability data and SHALL NOT define new trace collection.

#### Scenario: View surfaces aggregated metrics
- **WHEN** an admin opens the observability page of "ops-bot" which has had multiple calls in the last 24 hours
- **THEN** the response shows "ops-bot"'s call count, token/cost usage, error rate, average latency, permission_gate trigger/approval stats, and a recent-session list scoped to that agent

#### Scenario: Drill down to a single session trace
- **WHEN** an admin clicks a session in "ops-bot"'s recent-session list
- **THEN** the system links to that single session's full trace via the existing observability single-session trace query

#### Scenario: Aggregation is read-only over observability
- **WHEN** the per-agent view is computed
- **THEN** it reads from the observability traces without creating new collection points or modifying the trace schema

#### Scenario: Viewer may read the observability view
- **WHEN** a viewer opens an agent's observability page
- **THEN** the aggregated metrics are returned (read access is allowed for viewer)
