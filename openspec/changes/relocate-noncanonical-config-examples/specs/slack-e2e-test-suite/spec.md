## ADDED Requirements

### Requirement: Slack E2E sample agent is a test fixture

The Slack E2E sample agent SHALL live with the Slack E2E scenarios or test fixtures
rather than under the active deployment `config/` directory.

#### Scenario: Sample agent lives with Slack E2E assets
- **WHEN** an operator reads the Slack E2E setup guide
- **THEN** it points to a sample agent under `tests/e2e/slack_scenarios/` or a test fixture path
- **AND** it does not instruct copying from `config/agents/e2e-tester/`
