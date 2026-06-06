# slack-e2e-test-suite Specification

## Purpose
TBD - created by archiving change slack-e2e-test-suite. Update Purpose after archive.
## Requirements
### Requirement: Chinese scenario catalog

The suite SHALL define scenarios as YAML files under `tests/e2e/slack_scenarios/`, one
goal-driven scenario per file. Each file MUST contain `id`, `coverage` (list of tags),
`persona`, `goal`, `success_criteria`, `max_turns`, and `channel`, with an optional
`setup_hint`. `persona`, `goal`, and `success_criteria` MUST be written in Chinese.

#### Scenario: A scenario file is well-formed and Chinese

- **WHEN** a scenario file is loaded
- **THEN** it has all required fields, `id` is unique across the catalog, and
  `persona`/`goal`/`success_criteria` are non-empty and contain Chinese (CJK) text

#### Scenario: Coverage tags are from the agreed set

- **WHEN** the catalog is validated
- **THEN** every `coverage` tag is a member of the frozen coverage set and no scenario
  carries an unknown tag

### Requirement: Coverage completeness

The catalog SHALL include at least one scenario for every area in the agreed coverage
set: `chat`, `memory-in-session`, `memory-cross-session`, `clarify`, `tools`,
`tools-multi`, `mcp`, `skills`, `capability-absent`, `sandbox`, `sandbox-error`,
`image`, `image-text`, `prompt-injection`, `long-text`, `junk-input`,
`thread-continuity`.

#### Scenario: Every coverage area is represented

- **WHEN** the catalog is validated
- **THEN** each area in the coverage set is tagged by at least one scenario; a missing
  area fails validation

### Requirement: LLM-as-user black-box execution

The driver SHALL simulate a human user via the Claude Slack MCP: send the persona's
opening message to the scenario `channel`, then read the agent's in-thread replies and
improvise further Chinese turns toward the `goal` until the goal is met or `max_turns`
user messages have been sent. Pass/fail SHALL be judged from the Slack conversation
transcript only; the driver MUST NOT read fleetent internal logs.

#### Scenario: Goal-driven multi-turn conversation

- **WHEN** a scenario runs
- **THEN** the driver opens a thread, reads the agent's replies from that thread, and
  continues in Chinese toward the goal within the turn budget

#### Scenario: Verdict is transcript-only

- **WHEN** the driver judges a scenario
- **THEN** the pass/fail decision is based solely on the Slack transcript against
  `success_criteria`, with a stated reason

### Requirement: Honesty rules

The driver SHALL NOT mark a scenario `pass` without having read a real agent reply from
the thread. When a precondition is missing (MCP not authenticated, channel unset, server
or bot unavailable), the driver SHALL report the run as blocked and MUST NOT fabricate a
conversation or verdict.

#### Scenario: Missing precondition is reported, not faked

- **WHEN** the Slack MCP is unavailable or the scenario `channel` is unset
- **THEN** the driver reports the scenario as blocked with the missing precondition and
  records no synthetic transcript

### Requirement: Catalog validator (automated gate)

The system SHALL provide a pytest at `tests/integration/test_slack_scenarios_catalog.py`
that enforces the catalog requirements above (well-formedness, unique ids, valid coverage
tags, coverage completeness, Chinese content) and runs as part of the normal test suite.

#### Scenario: Validator fails on an incomplete catalog

- **WHEN** a coverage area has no scenario, or a scenario is missing a required field or
  has non-Chinese `goal`/`success_criteria`
- **THEN** the validator test fails, identifying the offending area or file

### Requirement: Slack E2E sample agent is a test fixture

The Slack E2E sample agent SHALL live with the Slack E2E scenarios or test fixtures
rather than under active deployment directories.

#### Scenario: Sample agent lives with Slack E2E assets
- **WHEN** an operator reads the Slack E2E setup guide
- **THEN** it points to a sample agent under `tests/e2e/slack_scenarios/` or a test fixture path
- **AND** it does not instruct copying from an active Agent deployment directory
