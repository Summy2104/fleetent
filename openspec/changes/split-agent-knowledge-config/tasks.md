## 1. Agent-side knowledge schema

- [ ] 1.1 Write failing tests: Agent config accepts `knowledge.bindings[]` and `retrieval_policy`; rejects old `knowledge_base.google_drive.connectors[]` / `knowledge_base.confluence.connectors[]`; validates duplicate defaults and missing binding fields
- [ ] 1.2 Implement: add Agent-side `knowledge` schema to `AgentFile`, remove Agent-side KB source connector schema, and expose the policy on Agent snapshots
- [ ] 1.3 Verify green: run `uv run pytest tests/unit/test_agent_config.py -x -q`

## 2. Knowledge service config schema

- [ ] 2.1 Write failing tests: parse `<FLEETENT_HOME>/config/knowledge.yaml` with `knowledge_bases[].sources[]`; validate source id uniqueness, source type required fields, secret env refs, indexing and sync defaults
- [ ] 2.2 Implement: add KB config parser/snapshot under `intelligence.knowledge_base` and path helper for `paths.config_dir() / "knowledge.yaml"`
- [ ] 2.3 Verify green: run the new KB config unit tests

## 3. KB operations integration

- [ ] 3.1 Write failing tests: `list_configured_connectors`, `get_connector_config`, `check_connector`, and `run_connector_sync` read from `knowledge.yaml`/snapshot rather than AgentFile legacy `knowledge_base` block
- [ ] 3.2 Implement: adapt KB operations to unified `sources[]` while preserving connector status semantics
- [ ] 3.3 Verify green: run `uv run pytest tests/unit/test_knowledge_connector_operations.py -x -q`

## 4. Platform materialization

- [ ] 4.1 Write failing tests: platform deploy writes Agent `knowledge.bindings[]` to `<agent-home>/agent.yaml` and KB construction config to `<FLEETENT_HOME>/config/knowledge.yaml`; `.env` seeding preserves source credential env values
- [ ] 4.2 Implement: update platform materialize/export paths and examples
- [ ] 4.3 Verify green: run related platform integration tests

## 5. Examples and docs

- [ ] 5.1 Write failing tests or validation checks: example `agent.yaml` and `knowledge.yaml` parse successfully and contain no inline secrets
- [ ] 5.2 Implement: update `config/agent/agent.yaml.example` and local `config/agent.yaml`; add `config/knowledge.yaml.example` or OpenSpec examples; remove old nested connector examples
- [ ] 5.3 Verify green: parse YAML examples in CI-safe tests

## 6. Quality gates

- [ ] 6.1 Run `uv run pytest -x -q`
- [ ] 6.2 Run `uv run ruff format src tests`
- [ ] 6.3 Run `uv run ruff check src tests`
- [ ] 6.4 Run `uv run mypy src`
- [ ] 6.5 Run `uv run python scripts/check_test_layers.py`
- [ ] 6.6 Run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
