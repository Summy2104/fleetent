## 1. Active config directory contract

- [ ] 1.1 Write failing tests: active `config/` contains only `agent/` and `platform/`; `config/agents/` and `config/knowledge-service/` do not exist; canonical deployment docs do not point at moved paths.
- [ ] 1.2 Implement: remove/move noncanonical directories and update path references.
- [ ] 1.3 Verify green: run relevant deployment docs/config tests.

## 2. Slack E2E sample agent relocation

- [ ] 2.1 Write failing tests or checks: Slack E2E README references the new local sample path and no longer references `config/agents/e2e-tester`.
- [ ] 2.2 Implement: move sample agent to E2E scenario/fixture path and update README.
- [ ] 2.3 Verify green: run Slack E2E docs/static checks if present.

## 3. Remove standalone Knowledge Service examples

- [ ] 3.1 Write failing tests: `config/knowledge-service/` and `examples/knowledge-service/` do not exist; tests/specs no longer require repository standalone Knowledge Service templates.
- [ ] 3.2 Implement: remove templates and update `config/platform/platform.yaml.example`, docs/tests/specs to treat standalone Knowledge Service examples as deferred.
- [ ] 3.3 Verify green: run `tests/unit/test_knowledge_service_config.py` and deployment docs tests.

## 4. OpenSpec and quality gates

- [ ] 4.1 Update specs for configuration, knowledge-service-config, and slack-e2e-test-suite.
- [ ] 4.2 Run `openspec validate relocate-noncanonical-config-examples --strict`.
- [ ] 4.3 Run targeted pytest / ruff checks.
