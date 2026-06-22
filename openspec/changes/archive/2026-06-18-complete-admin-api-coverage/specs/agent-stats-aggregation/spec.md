## MODIFIED Requirements

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
