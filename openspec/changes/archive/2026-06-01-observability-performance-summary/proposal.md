## Why

`observability-runtime-event-coverage` added detailed agent runtime events, but engineers still need a simple
query API that answers where time and failures are concentrated. Existing `get_usage_summary()` answers token
usage and completed run counts from `agent_run_completed`; it does not summarize LLM latency, tool latency,
fallback frequency, permission wait time, or failure rates.

This change adds a performance-oriented summary API on top of trace events so later platform views,
reflection evaluation, and operational debugging can use one stable contract.

## What Changes

- Add `get_performance_summary(PerformanceQuery) -> PerformanceSummary`.
- Aggregate completed/failed run lifecycle, LLM, fallback, tool, and permission events from existing traces.
- Support the same high-level filters as usage summary: user、agent、tenant、session、time range and limit.
- Compute success/failure counts, failure rate, average elapsed, p50 and p95 latency. `run_count` means
  terminal runs: `completed_count + failed_count`.
- Group LLM metrics by model and tool metrics by tool name.
- Tolerate missing fields, old traces, malformed payload values, and incomplete event streams.
- Update observability docs and roadmap M1 status.

## Out of Scope

- No rollup table or materialized metrics store.
- No direct SQL access from the summary API; it must read through `query_trace_events()`.
- No HTTP endpoint, admin CLI, dashboard, alerting, Prometheus, OpenTelemetry, or APM integration.
- No budget enforcement or quota behavior.
- No new runtime events; this change consumes events produced by archived runtime event coverage.

## Module Boundary Impact

- **Owning package**: `observability`.
- **Public API surface**: `PerformanceQuery`, `PerformanceSummary`, grouped model/tool/permission summary
  dataclasses, and `get_performance_summary()`.
- **Owned tables**: none; reads existing `traces` through public trace API.
- **Config namespace**: none.
- **Cross-module dependencies**: platform / reflection may call the new public API later; this change itself only
  depends on observability trace events.
- **Migration / shim plan**: none; additive public API.
