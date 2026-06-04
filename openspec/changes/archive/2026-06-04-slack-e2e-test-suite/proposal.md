## Why

fleetent agents are reachable over Slack (per-agent Socket Mode connector), but we have
no automated way to verify the **real Slack ↔ agent** round-trip and the agent's
behaviour the way a user actually experiences it — in Chinese, multi-turn, end to end.
Existing tests cover the engine deterministically at the `route()`/loop/tool layers
(LLM mocked); this is the opposite end: a black-box acceptance suite where an **LLM
plays a human user** over real Slack and a judge decides pass/fail from the
conversation alone.

## What Changes

- Add a **black-box Slack E2E suite** driven by an LLM-simulated user via the Claude
  Slack MCP (`mcp__claude_ai_Slack__*`). The user is goal-driven and converses in
  **Chinese**, multi-turn; a judge decides pass/fail from the Slack transcript only.
- Add a **catalog of ~17 Chinese scenario files** covering the agent's user-facing
  behaviours (conversation/memory, tools/MCP/skills/sandbox, multimodal,
  robustness/safety, IM threading).
- Add a reusable **Claude Code driver skill** `slack-agent-e2e` (executor + judge +
  honesty rules) that runs the scenarios in an authenticated session.
- Add a **sample test agent** (`config/agents/e2e-tester/agent.yaml.example`) with all
  capabilities enabled, and a **runbook**.
- Add a **pytest catalog validator** (`tests/integration/test_slack_scenarios_catalog.py`)
  so the suite has real red/green: every scenario file is structurally valid, ids are
  unique, coverage tags are from the agreed set, all coverage areas are represented, and
  persona/goal/success_criteria are non-empty Chinese (contain CJK).

Build-only: the suite is authored and validated by pytest now; actually running against
a live Slack workspace is triggered later. Out of scope (deferred): approval-flow,
per-agent routing, and allowlist-rejection scenarios; headless/cron execution (the Slack
MCP is interactively authenticated).

## Capabilities

### New Capabilities
- `slack-e2e-test-suite`: the Chinese scenario catalog format + coverage set, the
  LLM-as-user black-box test method (goal-driven multi-turn over the Slack MCP,
  transcript-only judging, honesty rules), and the catalog validator that enforces
  structural completeness.

### Modified Capabilities
<!-- none: purely additive dev/test tooling -->

## Impact

- **New files**: `tests/e2e/slack_scenarios/*.yaml` (Chinese scenarios) + `README.md`
  runbook; `.claude/skills/slack-agent-e2e/SKILL.md`; `config/agents/e2e-tester/agent.yaml.example`;
  `tests/integration/test_slack_scenarios_catalog.py`.
- **No production code changes**; no new runtime dependencies (reuses `pyyaml`; the
  validator runs under the existing pytest).
- **Runtime to actually execute** (not provisioned here): a test Slack workspace + bot,
  a running test agent, the Slack MCP authenticated to the channel, and the MCP user on
  the allowlist.
