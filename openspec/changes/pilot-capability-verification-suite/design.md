## Overview

This change adds a verification layer around the owner roadmap. It is intentionally test/report focused:
the implementation should not change product behavior unless a newly added failing test exposes an existing
contract bug.

## Test Layers

### Capability contract integration tests

Each owner capability domain gets at least one focused integration test that exercises a public boundary with
isolated dependencies:

- Observability: trace events, usage/performance summaries, diagnostics export and redaction.
- Memory: item lifecycle, retention/compaction, Shared Memory namespace and tenant/team isolation.
- Long-term Context: source selection, budget decisions, source attribution and ownership-based policy.
- Reflection: report generation, proposal lifecycle, KB reflection and trend aggregation.
- Vector Store: namespace isolation, reindex dry-run/apply, embedding/rerank provider abstraction.
- Knowledge Base: local ingest, parser dispatch, sync planner, fake connector, hybrid/graph/rerank planner.
- Deployment / Config: config fail-fast, upgrade/backup dry-run, diagnostics bundle boundaries.

These tests belong under `tests/integration/` unless they are pure deterministic scoring fixtures, in which case
they belong under `tests/evaluation/`.

### Pilot acceptance E2E smoke

E2E tests should stay few and user-path oriented. The target set is:

- local KB ingest -> agent KB binding -> agent query -> source attribution evidence;
- memory proposal/apply -> later context injection evidence;
- one agent run -> admin query trace/usage/performance evidence;
- reflection report/proposal lifecycle from persisted signals;
- fake connector check/dry-run/sync/latest-status;
- config failure with actionable error;
- backup/restore or Docker Compose smoke when explicitly enabled.

Default E2E must use local/fake/dry-run dependencies. Real provider and SaaS smoke are opt-in and skipped with
clear reasons when credentials or flags are missing.

## Verification Report

The report generator should produce both Markdown and JSON. Markdown is for human review; JSON is for CI and
future dashboard ingestion.

Minimum sections:

- run metadata: git SHA, Python version, command list, timestamp;
- automated checks: ruff, mypy, pytest by layer, coverage summary, module boundary check;
- capability evidence: one section per owner capability with pass/fail/skipped and artifact paths;
- real smoke evidence: LLM, embedding, rerank, Google Drive, Confluence, Docker Compose, each with skip reason;
- issue classification: `Pilot blocker`, `Docs gap`, `Enhancement`, `Out-of-scope`;
- final recommendation: `Go`, `Conditional Go`, or `No-Go`.

## Module Boundary Rules

Tests and report scripts must call migrated package public APIs or existing CLI/HTTP boundaries. If a needed
assertion currently requires importing an internal implementation, the implementation task should first add a
small public query/helper boundary or move the assertion to a higher-level black-box test.

## Risk

The main risk is creating slow or brittle E2E tests. Keep E2E coverage narrow, use integration tests for most
contracts, and make real external smoke explicitly opt-in.
