## Context

Agents speak to users over Slack via a per-agent Socket Mode connector; the receiving
connection identifies the agent and `normalizer.route` runs the loop. We want an
automated, high-fidelity, **Chinese** acceptance check of that path. The Claude Slack
MCP (`mcp__claude_ai_Slack__*`) can post/read in Slack as the authenticated user, so a
Claude Code session can play the human. Verification is black-box (Slack transcript
only), matching what a human reviewer sees.

## Goals / Non-Goals

**Goals**
- ~17 Chinese, goal-driven scenarios covering user-facing agent behaviour.
- An LLM-as-user driver (Claude Code skill) that runs each scenario multi-turn over the
  Slack MCP and judges pass/fail from the transcript, with honesty rules.
- A pytest validator giving real red/green over the catalog (structure + completeness +
  Chinese content).
- Build + validate now; live execution later.

**Non-Goals**
- Headless/cron runs (MCP is interactively authed).
- White-box/trace assertions (judging is transcript-only).
- Approval-flow, per-agent routing, allowlist-rejection scenarios (deferred).

## Decisions

### D1: LLM-as-user over real Slack via the Claude Slack MCP
User messages go out with `slack_send_message`; agent replies are read with
`slack_read_thread`/`slack_read_channel`. The MCP-authenticated identity is a real Slack
user, so the agent sees a normal user (not a bot). Reply correlation is by thread: the
opening message starts a thread; the agent replies in-thread; the user polls the thread
with a timeout + bounded retries.

### D2: Chinese, goal-driven scenarios
Each scenario file carries `persona`/`goal`/`success_criteria` in Chinese plus
`max_turns`, `channel`, `coverage` tags, and optional `setup_hint`. The user improvises
Chinese turns toward the goal (no fixed script), matching real usage.

### D3: Black-box judge with honesty rules
A judge reads the full transcript and decides pass/fail against `success_criteria`. It
never reads fleetent internals. The driver skill encodes honesty rules: no pass without
a real agent reply read from the thread; environment gaps are reported as blocked, never
faked.

### D4: Driver is a Claude Code skill
`slack-agent-e2e` (executor + judge) runs in an authenticated session. Rejected: a
pytest driver — the Slack MCP is a Claude Code tool, not a Python library, and is
interactively authed.

### D5: pytest catalog validator is the TDD anchor
`tests/integration/test_slack_scenarios_catalog.py` validates the YAML catalog: required
fields present; unique ids; `coverage` tags ⊆ the agreed set; every coverage area has ≥1
scenario (completeness); `persona`/`goal`/`success_criteria` non-empty and contain CJK
(Chinese). This makes "the suite is complete and well-formed" automatically verifiable,
so the otherwise-doc-heavy work has genuine red/green.

### D6: Coverage set (frozen for the validator)
`chat, memory-in-session, memory-cross-session, clarify, tools, tools-multi, mcp,
skills, capability-absent, sandbox, sandbox-error, image, image-text, prompt-injection,
long-text, junk-input, thread-continuity` — one scenario each (~17). The validator
asserts every tag is represented.

## Risks / Trade-offs

- **Nondeterminism**: both sides + judge are LLMs → occasional misjudgement. Mitigate
  with crisp Chinese `success_criteria`, turn budgets, re-runs. → The pytest validator
  is deterministic and is what gates CI; live runs are advisory.
- **Black-box**: cannot prove internal execution (accepted); trace oracle is a future
  add-on.
- **Image scenarios** need an image posted to Slack — verify MCP image-post capability
  before running; runbook documents the fallback.
- **MCP availability**: live runs only in an authenticated session.

## Migration Plan

Purely additive. 1) Add the pytest validator (red — no scenarios yet). 2) Author the
~17 Chinese scenarios (green). 3) Add the driver skill, sample agent, runbook. 4) Full
suite stays green; no production code touched. Rollback = delete the added files.

## Open Questions

- Whether to later add a trace-based oracle for the items that are weakly observable
  black-box (e.g. sandbox/MCP "really executed") — deferred.
