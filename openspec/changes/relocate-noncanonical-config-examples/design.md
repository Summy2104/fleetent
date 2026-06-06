## Decisions

### D1 — `config/` only contains active canonical templates

`config/` SHALL be read as “templates an operator may copy or that install/init scripts consume for the current default deployment.” It SHALL NOT contain optional service examples, legacy multi-agent scan examples, or E2E-only fixtures.

Allowed active directories:

```text
config/
  agent/
  platform/
```

### D2 — Non-canonical examples move by audience

- Human-readable optional deployment examples move to `examples/`.
- Test-only sample agents move next to the test scenario or under test fixtures.

Proposed paths:

```text
examples/knowledge-service/{knowledge.yaml.example,.env.example}
tests/e2e/slack_scenarios/agent.yaml.example
```

`config/agents/example` can be removed rather than moved if it duplicates `config/agent/agent.yaml.example`.

### D3 — Runtime multi-agent scan support is not removed

This change only relocates repository examples. It does not remove `agent_config.build_index(... agents_dir ...)` or `FLEETENT_AGENTS_DIR` support. Dev users can still point `FLEETENT_AGENTS_DIR` at any directory containing `<name>/agent.yaml`.
