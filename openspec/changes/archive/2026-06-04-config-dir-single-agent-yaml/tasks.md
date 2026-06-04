## 1. Runtime path contract

- [x] 1.1 Write failing tests: `paths.agent_file()` resolves to `config/agent.yaml`.
- [x] 1.2 Write failing tests: `agent_config.build_index()` loads config-dir `agent.yaml` as the sole default agent.
- [x] 1.3 Implement path and loader wording updates.
- [x] 1.4 Verify green: run `uv run pytest tests/unit/test_paths.py tests/unit/test_agent_config.py -x -q`.

## 2. Installer and template

- [x] 2.1 Write failing tests: install script seeds `$FLEETENT_HOME/config/agent.yaml` and preserves existing files.
- [x] 2.2 Update install script and `config/agent.yaml.example` comments.
- [x] 2.3 Verify green: run `uv run pytest tests/integration/test_install_script.py tests/integration/test_deployment_docs.py -x -q`.
- [x] 2.4 Run `openspec validate config-dir-single-agent-yaml --strict` and `openspec validate --all --strict`.

## 3. Local migration

- [x] 3.1 Move ignored local `agent.yaml` to ignored `config/agent.yaml` without committing it.
- [x] 3.2 Verify `config/agent.yaml` loads successfully and remains ignored.
