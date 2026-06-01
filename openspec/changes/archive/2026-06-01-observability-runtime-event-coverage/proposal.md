## Why

fleetent already has structured logs, SQLite trace storage, usage summary, and source attribution, but agent
runtime trace coverage is still too sparse. Today the reliable runtime events are mostly `injected_context`
and `agent_run_completed`; this is not enough to explain slow runs, failed tool chains, model fallback, human
approval pauses, context compression, or final streaming behavior.

This gap blocks later work:

- `observability-performance-summary` needs event-level duration and outcome data.
- `long-term-context-evaluation` needs to know what was injected and how the run proceeded.
- `reflection-report-evaluation` needs enough runtime evidence to distinguish bad findings from missing data.

## What Changes

- Extend agent runtime trace coverage with stable event types for run lifecycle, LLM calls, fallback, tool
  calls, permission decisions, context compression, final reply, and failures.
- Keep all runtime events in the existing observability `traces` table via `record_trace_event()`.
- Define minimum payload contracts for each event type.
- Keep trace payloads safe: no raw full prompt, no raw full reply, no unbounded tool arguments/results.
- Add integration contract tests for non-streaming and streaming agent runs.
- Update observability and intelligence roadmap docs to reflect the M1 work item.

## Out of Scope

- No new trace table or OpenTelemetry SDK.
- No dashboard, UI, or external APM integration.
- No performance rollup API in this change; `observability-performance-summary` will aggregate these events later.
- No new runtime governance behavior such as budgets, cancellation, loop detection, or parallel tool execution.
- No change to existing `agent_run_completed` or `injected_context` public contracts except correlating them with
  richer run events.

## Module Boundary Impact

- **Owning package**: `observability` owns event schema and persistence; `runtime` / legacy `agent_loop.py`
  emits runtime events through public observability APIs.
- **Public API surface**: reuse `TraceEvent` and `record_trace_event()`; optionally add small helper functions
  inside observability if that reduces duplication.
- **Owned tables**: existing observability-owned `traces`; no schema migration expected.
- **Config namespace**: none.
- **Cross-module dependencies**: agent-runtime depends on observability public API; context compression and
  permission gate outcomes are represented as trace events but remain owned by their modules.
- **Migration / shim plan**: none; this is additive trace coverage.
