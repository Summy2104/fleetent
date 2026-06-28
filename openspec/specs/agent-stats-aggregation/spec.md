# agent-stats-aggregation Specification

## Purpose
TBD - created by archiving change 2026-06-02-agent-statistics-panel. Update Purpose after archive.
## Requirements
### Requirement: Per-agent core metrics panel

The system SHALL aggregate, per `agent_id` over a selected time range, the core metrics that are directly derivable from existing trace fields: call count, distinct active users / channels / sessions, token usage (prompt / completion / total totals and per-call averages), latency (avg / P50 / P95), average turns per session, and a daily / weekly trend.

#### Scenario: Panel shows ready metrics for an agent
- **WHEN** an admin selects `ops-bot` and a time range in which it has runs
- **THEN** the panel shows its call count, active users / channels / sessions, token usage, P50 / P95 latency, and a by-day trend, all from currently available trace fields

#### Scenario: Aggregation reads through trace API
- **WHEN** the panel aggregates usage-class metrics
- **THEN** it reads traces through the observability trace query API (event_type `agent_run_completed`), not by directly querying the SQLite `traces` table

#### Scenario: Empty range yields zeros not errors
- **WHEN** the selected agent has no completed runs in the range
- **THEN** counts, tokens, and latency aggregate to 0 without raising

### Requirement: Multi-agent comparison view

The system SHALL support selecting multiple agents and rendering the same metric side by side for one-glance comparison, with a stable ordering.

#### Scenario: Compare two agents on a metric
- **WHEN** an admin selects `ops-bot` and `support-bot` and switches to the comparison view
- **THEN** the same metric (e.g. token usage, P95 latency) is shown side by side for both agents

#### Scenario: Stable comparison ordering
- **WHEN** multiple agents are compared on a metric
- **THEN** results are ordered deterministically (primary metric descending; ties broken by `agent_id` ascending)

### Requirement: Cost aggregation with model pricing

The system SHALL compute cost as `token × model unit price`, using the model pricing table provided by the model-provider capability. A model with no configured price SHALL display "未配置" rather than 0, and the panel SHALL highlight such unpriced models. While the pricing table is not yet available, the cost metric SHALL show a "待数据接入" placeholder.

#### Scenario: Cost computed for priced model
- **WHEN** a model used by the agent has input/output unit prices configured
- **THEN** its cost is computed as `token × unit price` and shown in the cost view

#### Scenario: Unpriced model shows not-configured
- **WHEN** a model used by the agent has no configured unit price
- **THEN** its cost shows "未配置" (not 0) and is highlighted as unpriced

#### Scenario: Pricing table absent shows placeholder
- **WHEN** the model pricing table is not yet available
- **THEN** the cost metric shows a "待数据接入" placeholder instead of erroring

### Requirement: Dependent fields show placeholder until available

Metrics that depend on v1.0 trace fields not yet emitted (termination-reason distribution, model fallback rate, context-compression count, skill hit, memory hit, sub_agent success) SHALL display a "待数据接入" placeholder rather than error or 0, and SHALL light up automatically once the underlying field is emitted. The `/admin/stats/*` data seams (`fetch_traces`, `fetch_approvals`, `pricing_table`) SHALL be wired to the real `fleetent.observability` public API and model-pricing table — they MUST NOT remain hardcoded empty (`return []` / `return None`) placeholders. Metrics whose source data exists (trace events, approvals, pricing) SHALL render real values; only genuinely not-yet-emitted fields SHALL show the placeholder.

#### Scenario: Stats seams return real observability data

- **WHEN** trace events and approvals exist for `ops-bot` in the range and an admin opens `/admin/stats/agents/{id}/overview`
- **THEN** call count, token usage, approval counts and cost render real aggregated values sourced from `fleetent.observability` and the pricing table — not empty/zero from a placeholder seam

#### Scenario: Genuinely-missing field still shows placeholder

- **WHEN** a metric depends on a trace field that agent-runtime does not yet emit
- **THEN** that metric shows "待数据接入"
- **AND** other metrics on the same panel backed by real data render normally

#### Scenario: Metric lights up after field is emitted

- **WHEN** a previously-missing dependent field begins appearing in trace payloads
- **THEN** the corresponding metric renders real values instead of the placeholder, without code changes to the field's emission

### Requirement: Tool and governance metrics

The system SHALL surface, per agent over the range: top tool-call ranking and average tools per run (parsed from trace `messages`), and permission_gate trigger count with approval pass / reject / timeout rates (from approvals).

#### Scenario: Approval rates visible
- **WHEN** `ops-bot` triggered permission_gate several times in the period
- **THEN** the governance group shows the approval trigger count and pass / reject / timeout rates

#### Scenario: Tool ranking parses messages tolerantly
- **WHEN** some traces in the range have incomplete or missing `messages` tool data
- **THEN** those are treated as no tool call and the top-tool ranking does not raise

### Requirement: allowed_tools coverage hint

The system SHALL list tools that are in an agent's `allowed_tools` allowlist but were never called in the selected period, marking each as "已授权未使用" to drive least-privilege narrowing.

#### Scenario: Unused authorized tool is flagged
- **WHEN** `ops-bot` has `write_file` in `allowed_tools` but never called it in the period
- **THEN** `write_file` is marked "已授权未使用" with a hint to consider removing it from the allowlist

#### Scenario: No false positive without runs
- **WHEN** the agent has an empty allowlist or no runs in the period
- **THEN** no tool is incorrectly flagged as unused

### Requirement: Model, skill and binding distribution

The system SHALL aggregate per agent: call / token / cost distribution by model and task_type, and binding facts (bound user / channel count and default-agent flag). Skill-hit, memory-hit, and sub_agent-success metrics SHALL follow the dependent-field placeholder rule until emitted.

#### Scenario: Distribution by model and binding facts shown
- **WHEN** an admin opens the model / binding group for an agent
- **THEN** the panel shows call / token distribution by model and task_type, plus bound user / channel counts and the default flag

### Requirement: Per-user usage and frequency ranking

The system SHALL provide, within a selected agent, a per-user ranking of token usage, call frequency (count / active days), and last-active time, sortable by any column; and a reverse "by user" view summarizing one user's usage and frequency across all agents.

#### Scenario: Per-user ranking under an agent
- **WHEN** an admin opens the per-user drilldown under `ops-bot`
- **THEN** each user's token usage, call frequency, and last-active are listed and sortable

#### Scenario: Reverse by-user summary
- **WHEN** an admin switches to the "by user" view for a user
- **THEN** that user's usage and frequency are summarized across all agents

### Requirement: Drilldown by user / channel / model / time

The system SHALL allow any agent metric to be sliced along user, channel, model, and time dimensions, with combined filters converging the data.

#### Scenario: Slice a metric by channel then time
- **WHEN** an admin drills the token-usage card and selects "by channel"
- **THEN** the metric splits by channel
- **AND** adding a time-range filter further narrows the data

### Requirement: Export and scheduled report

The system SHALL allow any panel view to be exported as CSV / image, and SHALL allow configuring a weekly / monthly email report of a chosen agent's statistics summary to admin mailboxes, reusing the scheduling capability.

#### Scenario: Export current view
- **WHEN** an admin clicks export on an agent's statistics view
- **THEN** the current view is exported as CSV / image

#### Scenario: Configure scheduled email report
- **WHEN** an admin configures a weekly email report for an agent
- **THEN** the report config is persisted via the scheduling capability and the summary is pushed to admin mailboxes on that schedule
- **AND** the configuration action is audited

### Requirement: Read-only access for viewer and admin

`/admin/stats/*` routes SHALL be readable by both `viewer` and `admin` (and `built_in_admin`) roles. The panel SHALL perform no write operations other than export and scheduled-report configuration. Per-user detail MAY be redacted for `viewer` per deployment policy.

#### Scenario: Viewer can browse read-only
- **WHEN** a `viewer` opens the statistics panel
- **THEN** read views (overview, comparison, drilldown) succeed

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to `/admin/stats/*` has no valid session
- **THEN** the response is 401

#### Scenario: Per-user detail redacted for viewer
- **WHEN** deployment policy enables per-user redaction and a `viewer` opens the per-user view
- **THEN** individual user identifiers are redacted while aggregate distributions remain visible
