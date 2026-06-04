## 1. Agent YAML intelligence config schema

- [x] 1.1 Write failing tests: `config/agent.yaml.example` loads as an `AgentFile` with typed intelligence config blocks.
- [x] 1.2 Write failing tests: an agent file accepts explicit vector / embedding / rerank / KB / long-term context config values.
- [x] 1.3 Implement schema support by reusing existing typed settings submodels.
- [x] 1.4 Verify green: run `uv run pytest tests/unit/test_agent_config.py -x -q`.

## 2. Template and docs consistency

- [x] 2.1 Move non-secret intelligence config examples into `config/agent.yaml.example`.
- [x] 2.2 Verify deployment docs/tests still assert global settings templates are removed.
- [x] 2.3 Run `uv run pytest tests/integration/test_deployment_docs.py -x -q`.
- [x] 2.4 Run `openspec validate agent-yaml-intelligence-config --strict` and `openspec validate --all --strict`.
