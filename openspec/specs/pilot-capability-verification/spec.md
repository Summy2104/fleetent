# pilot-capability-verification Specification

## Purpose
TBD - created by archiving change pilot-capability-verification-suite. Update Purpose after archive.
## Requirements
### Requirement: Owner capability contract tests

The project SHALL provide automated contract tests for the Pilot capability domains listed in
`docs/capabilities/roadmaps/pilot-readiness-roadmap.md`: Observability, Memory, Long-term Context,
Reflection, Vector Store, Knowledge Base and Deployment / Config. These tests SHALL exercise public APIs, CLI/HTTP
boundaries or documented admin entry points with isolated local dependencies. They SHALL NOT touch `data/`
or require real LLM, embedding, rerank, Google Drive or Confluence services by default.

#### Scenario: Contract tests run with isolated dependencies
- **WHEN** the default integration test suite is executed
- **THEN** owner capability contract tests use tmp SQLite, fake providers, fake connectors or deterministic fixtures
- **AND** no test requires external SaaS credentials by default

#### Scenario: Capability coverage is visible
- **WHEN** the verification report is generated
- **THEN** each owner capability domain is listed with pass, fail or skipped status
- **AND** each status includes the relevant test command or artifact path

### Requirement: Pilot acceptance E2E smoke tests

The project SHALL provide a small set of user-path E2E smoke tests that map to Pilot acceptance concerns.
These tests SHALL favor local/fake/dry-run execution by default and SHALL capture evidence that a human can
inspect. E2E tests SHALL remain narrow and SHALL NOT attempt to exhaustively cover all capability combinations.

#### Scenario: Local KB agent path produces source evidence
- **WHEN** a local knowledge document is ingested, bound to an agent and queried through the E2E harness
- **THEN** the response or trace evidence includes source attribution that a human can inspect

#### Scenario: Observability path produces queryable evidence
- **WHEN** an agent run completes through the E2E harness
- **THEN** admin query output can show trace, usage and performance evidence for that run

#### Scenario: Connector path exposes actionable status
- **WHEN** a fake connector check, dry-run sync and execute sync are run through the E2E harness
- **THEN** latest status output includes success/failure details and enough context for a human to classify issues

### Requirement: Explicit opt-in real smoke tests

Real LLM, embedding, rerank, Google Drive, Confluence and Docker Compose Pilot smoke tests SHALL be explicit
opt-in tests. When required flags or credentials are absent, these tests SHALL skip with clear reasons instead
of failing or silently passing.

#### Scenario: Real provider smoke is skipped by default
- **WHEN** default tests run without real smoke flags
- **THEN** real LLM, embedding and rerank smoke tests are skipped
- **AND** the skip reason names the missing flag or credential requirement

#### Scenario: Real SaaS connector smoke is skipped by default
- **WHEN** default tests run without SaaS smoke flags or credential refs
- **THEN** Google Drive and Confluence smoke tests are skipped
- **AND** the skip reason names the missing flag or credential requirement

### Requirement: Human-readable verification report

The project SHALL provide a verification report entry point that emits Markdown for human review and JSON for
automation. The report SHALL include run metadata, automated command results, per-capability evidence,
real smoke pass/fail/skipped status, issue classification and a final Go / Conditional Go / No-Go recommendation.

#### Scenario: Report includes command and artifact evidence
- **WHEN** the verification report is generated
- **THEN** it includes git SHA, Python version, timestamps, executed commands and artifact paths where available

#### Scenario: Report classifies issues by Pilot impact
- **WHEN** tests or smoke checks fail or are skipped
- **THEN** the report classifies each issue as `Pilot blocker`, `Docs gap`, `Enhancement` or `Out-of-scope`
- **AND** the final recommendation is one of `Go`, `Conditional Go` or `No-Go`

#### Scenario: Report supports manual review
- **WHEN** a human reviews the Markdown report
- **THEN** they can see which owner capability domains passed, failed or were skipped
- **AND** they can find the evidence needed to reproduce or inspect each result
