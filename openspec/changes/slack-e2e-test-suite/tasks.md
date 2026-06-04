## 1. Catalog validator (TDD anchor)

- [ ] 1.1 Write `tests/integration/test_slack_scenarios_catalog.py` (failing — no
  scenarios yet): load every `tests/e2e/slack_scenarios/*.yaml`; assert required fields
  present; `id` unique; `coverage` tags ⊆ the frozen set; every coverage area has ≥1
  scenario (completeness); `persona`/`goal`/`success_criteria` non-empty and contain CJK.
  Define the frozen coverage set in the test. Run `uv run pytest -x -q` → must be RED.

## 2. Chinese scenario catalog

- [ ] 2.1 Author the ~17 Chinese scenario YAMLs under `tests/e2e/slack_scenarios/`, one
  per coverage area: chat, memory-in-session, memory-cross-session, clarify, tools,
  tools-multi, mcp, skills, capability-absent, sandbox, sandbox-error, image, image-text,
  prompt-injection, long-text, junk-input, thread-continuity. `persona`/`goal`/
  `success_criteria` in Chinese; `channel` is the `REPLACE_WITH_TEST_CHANNEL` placeholder;
  add `setup_hint` where a scenario needs agent config (mcp/sandbox/skill/vision).
- [ ] 2.2 Run `uv run pytest tests/integration/test_slack_scenarios_catalog.py -q` → GREEN.

## 3. Driver skill

- [ ] 3.1 Write `.claude/skills/slack-agent-e2e/SKILL.md`: preconditions check; per-case
  loop (open thread → poll `slack_read_thread` with timeout/retry → improvise Chinese
  turns toward goal → stop at goal/`max_turns`); transcript-only judge rubric; report
  table (`id | coverage | result | turns | reason` + `PASSED n/m`); honesty rules
  (no pass without a real reply; report blocked, never fabricate).

## 4. Sample agent + runbook

- [ ] 4.1 Write `config/agents/e2e-tester/agent.yaml.example`: `connectors.slack`
  (env-ref tokens) + tools/skills/MCP/sandbox enabled so scenarios can exercise them.
- [ ] 4.2 Write `tests/e2e/slack_scenarios/README.md`: preconditions, how to trigger the
  skill, image-post caveat, deferred-scope note.

## 5. Closeout

- [ ] 5.1 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [ ] 5.2 Confirm the `e2e-tester` example dir is NOT picked up by `agent_config` scan
  (only `agent.yaml.example`, no `agent.yaml`).
- [ ] 5.3 Full suite `uv run pytest -x -q` green.
