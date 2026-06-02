## Why

`reflection-foundation` can generate structured reports from trace events and read-only memory
signals, but there is no evaluation baseline for finding quality. Without fixtures, changes to
trace payloads, memory search, finding rules, or future summarization can silently increase false
positives, miss obvious findings, or leak raw transcript text into persisted reports.

This change adds deterministic reflection report evaluation so maintainers can regression-test
expected findings, forbidden findings, and redaction behavior without calling a real LLM or any
external service by default.

## What Changes

- Add `tests/evaluation/` fixtures for reflection report scenarios.
- Add a reflection evaluation runner that:
  - loads fixture trace events and memory signals
  - patches observability and memory public APIs with deterministic fakes
  - calls `run_reflection(scope)`
  - validates expected finding types, summaries, evidence ids, and metadata
  - validates forbidden finding types/summaries are absent
  - validates persisted report payload does not contain forbidden transcript snippets
- Cover baseline cases:
  - repeated memory fact produces `memory_candidate`
  - conflicting memory signals produce `memory_conflict`
  - repeated task pattern produces `skill_opportunity`
  - negative/noisy traces do not produce findings
  - raw transcript snippets are not persisted
- Keep default evaluation isolated from `data/`, real LLM, embedding providers, KB connectors, and SaaS.
- Add an optional manual real-route smoke guard that defaults to skip.
- Update reflection docs and CI quality gate spec language so this evaluation remains manually runnable
  and outside the default PR gate.

## Out of Scope

- No LLM-graded report quality scoring.
- No automatic application of reflection findings.
- No memory writeback, skill proposal creation, or KB maintenance.
- No dashboard, admin UI, or scheduled job changes.
- No new persistent tables or migrations.
- No real LLM or SaaS calls in default tests.

## Dependencies

- Requires `reflection-foundation`.
- Depends on observability runtime events being available as evaluation fixture input, but default
  tests use fake public API responses.
- Complements `memory-reflection-maintenance`; it does not implement maintenance actions.

## Module Boundary Impact

- **Owning package**: no production owning package; this change belongs to reflection evaluation
  test ownership under `tests/evaluation`.
- **Public API surface**: no new production public API. The runner uses existing
  `fleetent.intelligence.reflection.run_reflection()`, `ReflectionReport`, and `ReflectionFinding`.
- **Owned tables**: none. Tests use `reflection_reports` through tmp SQLite when persistence
  assertions are needed.
- **Config namespace**: no production config. Optional real-route smoke uses explicit
  `FLEETENT_EVAL_*` environment variables only.
- **Cross-module dependencies**: tests patch observability `query_trace_events()` and
  `memory_layer.search()` public APIs; no internal observability or memory store access.
- **Migration / shim plan**: none.

## Impact

- **Code**: evaluation helper and tests only unless fixtures expose an existing reflection contract bug.
- **Tests**: new deterministic evaluation fixtures and pytest coverage in `tests/evaluation/`.
- **CI**: no default PR/main gate change; evaluation stays manually runnable.
- **Data**: no real user data and no writes under `data/`.
