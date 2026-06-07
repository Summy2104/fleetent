## 1. Canonical repository example layout

- [x] 1.1 Write failing tests: repository has `.env.example`, `platform.yaml.example`,
  `agents/default/agent.yaml.example`, and `agents/default/.env.example`; repository `config/`
  does not contain canonical templates or may be absent.
- [x] 1.2 Implement: move templates from `config/platform/` and `config/agent/` to their
  runtime-adjacent example paths; update `.gitignore`.
- [x] 1.3 Verify green: run deployment docs/config template tests.

## 2. Platform home init/install/docker paths

- [x] 2.1 Write failing tests: `fleetent-admin init-config` creates `.env` and
  `platform.yaml` from root examples; install creates `.env`, `platform.yaml`, and
  `agents/default/{agent.yaml,.env,data/}`; Docker Compose uses root `.env` and
  `platform.yaml`.
- [x] 2.2 Implement: update `init_config.py`, `scripts/install.sh`, `docker-compose.yml`,
  Docker/runtime docs, and path references.
- [x] 2.3 Verify green: run `tests/unit/test_admin_init_config.py`,
  `tests/integration/test_install_script.py`, and deployment docs tests.

## 3. Platform config loader and Knowledge embedded config

- [x] 3.1 Write failing tests: Platform embedded Knowledge config loads from
  `platform.yaml` / Platform DB snapshot, not `config/knowledge.yaml`; default repo does not ship
  or require `config/knowledge.yaml`.
- [x] 3.2 Implement: add/adjust Platform config loader; migrate `KnowledgeConfigSnapshot`
  file loading to read the `knowledge` section from `platform.yaml`; remove default
  `knowledge_config_path() -> config/knowledge.yaml` behavior.
- [x] 3.3 Verify green: run `tests/unit/test_knowledge_service_config.py`,
  `tests/unit/test_knowledge_connector_operations.py`, and KB connector admin tests.

## 4. Agent materialize and ENV boundary

- [x] 4.1 Write failing tests: materialize does not write `config/knowledge.yaml`; Agent `.env`
  excludes Platform-owned KB construction env vars while still including Agent model/MCP/connector
  env refs.
- [x] 4.2 Implement: remove/default-disable `write_knowledge_config()` from Agent materialize
  path; ensure Agent `.env` is derived only from Agent runtime config and Agent credential slots.
- [x] 4.3 Verify green: run Agent materialize and agent secret tests.

## 5. OpenSpec/docs cleanup

- [x] 5.1 Write failing checks/tests: specs/docs no longer mention root `.env.example` missing,
  `config/platform/*` examples, `config/agent/*` examples, default `config/knowledge.yaml`, or
  root `FLEETENT_HOME/agent.yaml` as current behavior.
- [x] 5.2 Implement: update `configuration`, `install-bootstrap`, `knowledge-service-config`,
  `file-agent-runtime`, `platform-agent-lifecycle`, README and deployment docs.
- [x] 5.3 Verify green: run `openspec validate root-platform-home-config-layout --strict`,
  `openspec validate --specs --strict`, and targeted docs tests.

## 6. Final quality gates

- [x] 6.1 Run `uv run pytest -x -q`.
- [x] 6.2 Run `uv run ruff check src tests`.
- [x] 6.3 Run `uv run python scripts/check_test_layers.py`.
